-- Production-specific SMS installation. Sending and scheduler remain OFF.
-- Common phone-level limits for selected seller automation channels.
CREATE OR REPLACE FUNCTION public.outreach_recipient_limits(p_phone text)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
WITH attempts AS (
  SELECT created_at,status IN ('submitting','unknown') AS unresolved FROM public.sms_events
    WHERE provider IN ('twilio','retell') AND direction='outbound' AND phone_number=p_phone
      AND NOT (coalesce(raw_payload,'{}'::jsonb) ? 'MessageSid')
  UNION ALL
  SELECT created_at,status<>'completed' FROM public.retell_call_requests WHERE phone_number=p_phone
)
SELECT jsonb_build_object('blocker', CASE
  WHEN EXISTS (SELECT 1 FROM attempts WHERE unresolved) THEN 'unresolved_attempt'
  WHEN (SELECT count(*) FROM attempts WHERE created_at>now()-interval '30 days')>=2 THEN 'attempt_limit'
  WHEN EXISTS (SELECT 1 FROM attempts WHERE created_at>now()-interval '24 hours') THEN 'contact_cooldown'
  ELSE NULL END);
$$;
REVOKE ALL ON FUNCTION public.outreach_recipient_limits(text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.outreach_recipient_limits(text) TO service_role;

-- Consent-bearing web forms only. Deployment does not enable sending or schedule a worker.
CREATE TABLE public.retell_form_sms_jobs (
  id uuid PRIMARY KEY,
  lead_id uuid NOT NULL REFERENCES public.leads(id),
  submission_id uuid NOT NULL UNIQUE REFERENCES public.lead_form_submissions(id),
  phone_number text NOT NULL CHECK (phone_number ~ '^\+1[2-9][0-9]{9}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  due_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'scheduled' CHECK (status IN ('scheduled','processing','accepted','stopped','review')),
  claimed_at timestamptz,
  chat_id text,
  reason text
);
CREATE INDEX retell_form_sms_due ON public.retell_form_sms_jobs(due_at) WHERE status='scheduled';
ALTER TABLE public.retell_form_sms_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.retell_form_sms_jobs FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.retell_form_sms_jobs TO service_role;

CREATE FUNCTION public.claim_retell_form_sms(p_limit int DEFAULT 3)
RETURNS SETOF public.retell_form_sms_jobs LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE j public.retell_form_sms_jobs;
BEGIN
  FOR j IN SELECT * FROM public.retell_form_sms_jobs WHERE status='scheduled' AND due_at<=now()
    ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT least(greatest(p_limit,1),10)
  LOOP
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('seller-outreach:'||j.phone_number,0));
    IF j.expires_at <= now() OR
       public.outreach_recipient_limits(j.phone_number)->>'blocker' IS NOT NULL OR
       coalesce((public.intake_phone_status(j.phone_number,j.lead_id,''))->>'suppressed','true') <> 'false' OR
       EXISTS (SELECT 1 FROM public.retell_form_sms_jobs r WHERE r.phone_number=j.phone_number
         AND r.id<>j.id AND r.status IN ('processing','accepted','review')) OR
       EXISTS (SELECT 1 FROM public.sms_events e WHERE e.phone_number=j.phone_number
         AND (e.opt_out IS TRUE OR (e.direction='outbound' AND e.created_at>now()-interval '24 hours'))) THEN
      UPDATE public.retell_form_sms_jobs SET status='stopped',reason='Expired, suppressed, or previous recipient contact' WHERE id=j.id;
      CONTINUE;
    END IF;
    UPDATE public.retell_form_sms_jobs SET status='processing',claimed_at=now() WHERE id=j.id RETURNING * INTO j;
    -- Shared ledger blocks Twilio's claim function from sending alongside Retell.
    INSERT INTO public.sms_events(id,lead_id,provider,direction,phone_number,body,status)
      VALUES(j.id,j.lead_id,'retell','outbound',j.phone_number,'Retell consented form response pending','submitting');
    RETURN NEXT j;
  END LOOP;
END; $$;
REVOKE ALL ON FUNCTION public.claim_retell_form_sms(int) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_retell_form_sms(int) TO service_role;

-- Cloud trigger only; both scheduler and application sending gates remain OFF.
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;
CREATE SCHEMA IF NOT EXISTS private;
-- Preserve existing private-schema grants used by production RLS helpers.
CREATE TABLE private.retell_sms_scheduler (
  singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
  enabled boolean NOT NULL DEFAULT false,
  endpoint text NOT NULL DEFAULT 'https://wholesale-automation.vercel.app/webhooks/_worker/retell-form-sms'
    CHECK(endpoint IN (
      'https://wholesale-automation-git-codex-dallas-de1768-julysses-projects.vercel.app/webhooks/_worker/retell-form-sms',
      'https://wholesale-automation.vercel.app/webhooks/_worker/retell-form-sms')),
  last_request_id bigint,
  last_requested_at timestamptz
);
ALTER TABLE private.retell_sms_scheduler ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.retell_sms_scheduler FROM PUBLIC, anon, authenticated, service_role;
INSERT INTO private.retell_sms_scheduler(singleton) VALUES(true);

CREATE FUNCTION private.tick_retell_sms() RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE c private.retell_sms_scheduler; bearer text; bypass text; headers jsonb; rid bigint;
BEGIN
  SELECT * INTO c FROM private.retell_sms_scheduler WHERE singleton FOR UPDATE;
  IF NOT FOUND OR NOT c.enabled THEN
    RETURN jsonb_build_object('status','disabled','requested',false);
  END IF;
  SELECT decrypted_secret INTO bearer FROM vault.decrypted_secrets WHERE name='retell_sms_worker_bearer';
  IF coalesce(bearer,'')='' THEN
    RETURN jsonb_build_object('status','missing_worker_credential','requested',false);
  END IF;
  headers := jsonb_build_object('Authorization','Bearer '||bearer);
  IF c.endpoint LIKE 'https://wholesale-automation-git-%' THEN
    SELECT decrypted_secret INTO bypass FROM vault.decrypted_secrets WHERE name='retell_sms_preview_bypass';
    IF coalesce(bypass,'')='' THEN
      RETURN jsonb_build_object('status','missing_preview_access','requested',false);
    END IF;
    headers := headers || jsonb_build_object('x-vercel-protection-bypass',bypass);
  END IF;
  -- Avoid overlapping HTTP workers. A crash cannot make the same processing job
  -- eligible again; the application moves ambiguous attempts to review.
  IF c.last_request_id IS NOT NULL AND c.last_requested_at > now()-interval '90 seconds'
     AND NOT EXISTS (SELECT 1 FROM net._http_response WHERE id=c.last_request_id) THEN
    RETURN jsonb_build_object('status','in_flight','requested',false);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.retell_form_sms_jobs
                   WHERE status='scheduled' AND due_at<=now())
     AND NOT EXISTS (SELECT 1 FROM public.retell_form_sms_jobs
                   WHERE status='processing' AND claimed_at<now()-interval '5 minutes') THEN
    RETURN jsonb_build_object('status','idle','requested',false);
  END IF;
  SELECT net.http_get(url:=c.endpoint, headers:=headers, timeout_milliseconds:=60000) INTO rid;
  UPDATE private.retell_sms_scheduler SET last_request_id=rid,last_requested_at=now() WHERE singleton;
  RETURN jsonb_build_object('status','requested','requested',true,'request_id',rid);
END; $$;
REVOKE ALL ON FUNCTION private.tick_retell_sms() FROM PUBLIC,anon,authenticated,service_role;
-- Registered inactive in the same transaction: installation cannot send.
DO $$
DECLARE jid bigint;
BEGIN
  jid := cron.schedule('wholesaleos-retell-form-sms','10 seconds','SELECT private.tick_retell_sms()');
  PERFORM cron.alter_job(jid,active:=false);
END; $$;
-- Preserve ordinary-reply handling for older webhook deployments without the derived classification.
-- Commit carrier replies, suppression, and follow-up together before any optional Retell handoff.
CREATE OR REPLACE FUNCTION public.record_twilio_event(p_event uuid, p_kind text, p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE
  v_phone text;
  v_lead uuid;
  v_inserted uuid;
  v_stop boolean;
  v_suppressed boolean;
  v_body text := coalesce(p_payload->>'Body','');
  v_control text := upper(trim(coalesce(p_payload->>'OptOutType',p_payload->>'Body','')));
BEGIN
  IF p_kind NOT IN ('inbound','status') OR coalesce(p_payload->>'MessageSid','') !~ '^SM[0-9a-fA-F]{32}$' THEN
    RAISE EXCEPTION 'Invalid Twilio event';
  END IF;
  v_phone := CASE WHEN p_kind='inbound' THEN p_payload->>'From' ELSE p_payload->>'To' END;
  IF coalesce(v_phone,'') !~ '^\+1[0-9]{10}$' THEN RAISE EXCEPTION 'Invalid phone'; END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('seller-outreach:'||v_phone,0));
  v_stop := p_kind='inbound' AND (v_control IN ('STOP','STOPALL','UNSUBSCRIBE','CANCEL','END','QUIT','REVOKE','OPTOUT','OPT OUT')
    OR coalesce(p_payload->>'crm_opt_out','false')='true'
    OR upper(trim(v_body)) IN ('STOP','STOPALL','UNSUBSCRIBE','CANCEL','END','QUIT','REVOKE','OPTOUT','OPT OUT'));
  IF p_kind='status' THEN
    IF p_payload->>'app_message_id' IS NOT NULL THEN
      SELECT lead_id INTO v_lead FROM public.sms_events WHERE id=(p_payload->>'app_message_id')::uuid
        AND provider='twilio' AND direction='outbound' AND phone_number=v_phone;
    ELSE
      SELECT lead_id INTO v_lead FROM public.sms_events WHERE provider='twilio'
        AND raw_payload->>'provider_sid'=p_payload->>'MessageSid' LIMIT 1;
    END IF;
  ELSE
    SELECT id INTO v_lead FROM public.leads l WHERE EXISTS (
      SELECT 1 FROM unnest(ARRAY[l.owner_phone_1,l.owner_phone_2,l.owner_phone_3]) n(phone)
      WHERE regexp_replace(regexp_replace(coalesce(n.phone,''),'[^0-9]','','g'),'^1([0-9]{10})$','\1')=right(v_phone,10)
    ) ORDER BY created_at DESC LIMIT 1;
  END IF;
  INSERT INTO public.sms_events(id,lead_id,provider,direction,phone_number,body,status,opt_out,raw_payload)
    VALUES(p_event,v_lead,'twilio',CASE WHEN p_kind='inbound' THEN 'inbound' ELSE 'outbound' END,
      v_phone,v_body,CASE WHEN p_kind='inbound' THEN 'replied' ELSE p_payload->>'MessageStatus' END,v_stop,p_payload)
    ON CONFLICT(id) DO NOTHING RETURNING id INTO v_inserted;
  IF v_inserted IS NULL THEN RETURN jsonb_build_object('saved',true,'duplicate',true); END IF;
  IF v_stop THEN
    -- Store even unknown numbers so a later imported lead remains suppressed.
    INSERT INTO public.dnc_registry(id,phone_number,lead_id,reason,source,opt_out_keyword,raw_payload)
      VALUES(p_event,v_phone,v_lead,'opt_out','twilio',left(v_body,100),p_payload) ON CONFLICT(id) DO NOTHING;
    UPDATE public.leads l SET dnc=true,status='dnc',sms_sequence_active=false,email_sequence_active=false,ai_calling_paused=true
      WHERE EXISTS (SELECT 1 FROM unnest(ARRAY[l.owner_phone_1,l.owner_phone_2,l.owner_phone_3]) n(phone)
        WHERE regexp_replace(regexp_replace(coalesce(n.phone,''),'[^0-9]','','g'),'^1([0-9]{10})$','\1')=right(v_phone,10));
    UPDATE public.tasks t SET status='cancelled'
      WHERE t.status='pending' AND t.type='acquisition_review'
        AND t.title IN ('Retell SMS reply: review and follow up','SMS reply: review and follow up')
        AND EXISTS (SELECT 1 FROM public.leads l WHERE l.id=t.lead_id AND EXISTS (
          SELECT 1 FROM unnest(ARRAY[l.owner_phone_1,l.owner_phone_2,l.owner_phone_3]) n(phone)
          WHERE regexp_replace(regexp_replace(coalesce(n.phone,''),'[^0-9]','','g'),'^1([0-9]{10})$','\1')=right(v_phone,10)));
  ELSIF p_kind='inbound' AND v_control NOT IN ('START','UNSTOP','YES','HELP','INFO') THEN
    UPDATE public.leads SET status='responding',sms_sequence_active=false,ai_calling_paused=true
      WHERE id=v_lead AND dnc IS FALSE AND status NOT IN ('dead','dnc','closed');
  END IF;
  v_suppressed := coalesce((public.intake_phone_status(v_phone,v_lead,''))->>'suppressed','true') <> 'false';
  IF p_kind='inbound' AND NOT v_stop AND NOT v_suppressed AND v_lead IS NOT NULL
    AND v_control NOT IN ('START','UNSTOP','YES','HELP','INFO') THEN
    INSERT INTO public.tasks(id,lead_id,title,description,priority,status,type)
      SELECT p_event,v_lead,'SMS reply: review and follow up',
        'Carrier SMS receipt: '||p_event::text||E'\nRecipient text (unverified): '||left(v_body,3000),
        'high','pending','acquisition_review'
      WHERE EXISTS (SELECT 1 FROM public.leads WHERE id=v_lead AND dnc IS FALSE
        AND status NOT IN ('dead','dnc','closed','sold'))
      ON CONFLICT(id) DO NOTHING;
  END IF;
  -- START is recorded, but never automatically clears existing DNC or renews consent.
  IF p_kind='inbound' THEN
    INSERT INTO public.app_notifications(id,recipient_role,type,title,body,action_url,lead_id,metadata)
      VALUES(p_event,'admin','pipeline_step',CASE WHEN v_stop THEN 'SMS opt-out received' ELSE 'SMS reply received' END,
        left(v_body,500),'/leads',v_lead,jsonb_build_object('provider','twilio','message_sid',p_payload->>'MessageSid','opt_out',v_stop));
  END IF;
  RETURN jsonb_build_object('saved',true,'duplicate',false,'lead_id',v_lead,
    'suppressed',v_suppressed,'opt_out',v_stop);
END;
$$;
REVOKE ALL ON FUNCTION public.record_twilio_event(uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.record_twilio_event(uuid,text,jsonb) TO service_role;
