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
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('twilio-sms:'||j.phone_number,0));
    IF j.expires_at <= now() OR
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

-- Use the same phone lock and count Retell receipts in the existing Twilio gate.
CREATE OR REPLACE FUNCTION public.claim_twilio_sms(p_id uuid,p_lead uuid,p_phone text,p_body text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v_id uuid; v_count int;
BEGIN
  IF coalesce(p_phone,'') !~ '^\+1[2-9][0-9]{9}$' OR length(coalesce(p_body,'')) NOT BETWEEN 1 AND 1600 THEN
    RAISE EXCEPTION 'Invalid SMS claim';
  END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('twilio-sms:'||p_phone,0));
  IF EXISTS (SELECT 1 FROM public.sms_events WHERE id=p_id) THEN
    RETURN jsonb_build_object('claimed',false,'reason','existing_reference');
  END IF;
  IF EXISTS (SELECT 1 FROM public.sms_events WHERE provider IN ('twilio','retell') AND direction='outbound'
      AND phone_number=p_phone AND status IN ('submitting','unknown')) THEN
    RETURN jsonb_build_object('claimed',false,'reason','unresolved_attempt');
  END IF;
  IF coalesce((public.intake_phone_status(p_phone,p_lead,''))->>'suppressed','true') <> 'false' THEN
    RETURN jsonb_build_object('claimed',false,'reason','suppressed');
  END IF;
  -- Status callbacks are archives, not additional send attempts.
  SELECT count(*) INTO v_count FROM public.sms_events WHERE provider IN ('twilio','retell') AND direction='outbound'
    AND phone_number=p_phone AND NOT (coalesce(raw_payload,'{}'::jsonb) ? 'MessageSid')
    AND created_at > now()-interval '30 days';
  IF v_count >= 2 THEN RETURN jsonb_build_object('claimed',false,'reason','attempt_limit'); END IF;
  IF EXISTS (SELECT 1 FROM public.sms_events WHERE provider IN ('twilio','retell') AND direction='outbound'
    AND phone_number=p_phone AND NOT (coalesce(raw_payload,'{}'::jsonb) ? 'MessageSid')
    AND created_at > now()-interval '24 hours') THEN
    RETURN jsonb_build_object('claimed',false,'reason','contact_cooldown');
  END IF;
  INSERT INTO public.sms_events(id,lead_id,provider,direction,phone_number,body,status)
    VALUES(p_id,p_lead,'twilio','outbound',p_phone,p_body,'submitting')
    ON CONFLICT(id) DO NOTHING RETURNING id INTO v_id;
  RETURN jsonb_build_object('claimed',v_id IS NOT NULL,'reason',CASE WHEN v_id IS NULL THEN 'existing_reference' ELSE 'claimed' END);
END; $$;
REVOKE ALL ON FUNCTION public.claim_twilio_sms(uuid,uuid,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_twilio_sms(uuid,uuid,text,text) TO service_role;

