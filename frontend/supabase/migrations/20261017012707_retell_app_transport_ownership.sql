-- Dormant app-owned transport ledger. No backfill of attempted jobs, scheduler,
-- provider request or activation. Existing rows remain retell_native.
ALTER TABLE public.retell_form_sms_jobs
 ADD COLUMN delivery_transport text NOT NULL DEFAULT 'retell_native'
 CHECK(delivery_transport IN ('retell_native','app_twilio')),
 ADD COLUMN delivery_body text,
 ADD COLUMN delivery_sender text,
 ADD CONSTRAINT retell_form_transport_payload CHECK(
  (delivery_transport='retell_native' AND delivery_body IS NULL AND delivery_sender IS NULL)
  OR (delivery_transport='app_twilio' AND length(trim(delivery_body)) BETWEEN 1 AND 1600
      AND delivery_sender ~ '^\+1[2-9][0-9]{9}$' AND delivery_body IS NOT NULL AND delivery_sender IS NOT NULL));

CREATE FUNCTION public.protect_retell_form_transport() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF ROW(NEW.delivery_transport,NEW.delivery_body,NEW.delivery_sender,NEW.lead_id,NEW.submission_id,NEW.phone_number)
   IS DISTINCT FROM ROW(OLD.delivery_transport,OLD.delivery_body,OLD.delivery_sender,OLD.lead_id,OLD.submission_id,OLD.phone_number) THEN
  RAISE EXCEPTION 'Inquiry transport identity and content are immutable';
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.protect_retell_form_transport() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER protect_retell_form_transport BEFORE UPDATE ON public.retell_form_sms_jobs
 FOR EACH ROW EXECUTE FUNCTION public.protect_retell_form_transport();

CREATE FUNCTION public.claim_retell_form_sms_transport(p_limit integer, p_job uuid, p_transport text)
 RETURNS SETOF public.retell_form_sms_jobs
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE j public.retell_form_sms_jobs;
BEGIN
  IF p_transport IS NULL OR p_transport NOT IN ('retell_native','app_twilio') THEN RAISE EXCEPTION 'Invalid delivery transport'; END IF;
  FOR j IN SELECT * FROM public.retell_form_sms_jobs WHERE status='scheduled' AND due_at<=now() AND delivery_transport=p_transport
    AND (p_job IS NULL OR id=p_job)
    ORDER BY due_at FOR UPDATE SKIP LOCKED LIMIT CASE WHEN p_job IS NOT NULL THEN 1 ELSE least(greatest(p_limit,1),10) END
  LOOP
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('seller-outreach:'||j.phone_number,0));
    IF j.expires_at <= now() OR
       public.outreach_recipient_limits(j.phone_number)->>'blocker' IS NOT NULL OR
       coalesce((public.intake_phone_status(j.phone_number,j.lead_id,''))->>'suppressed','true') <> 'false' OR
       EXISTS (SELECT 1 FROM public.retell_form_sms_jobs r WHERE r.phone_number=j.phone_number
         AND r.id<>j.id AND r.status IN ('processing','accepted','review')) OR
       EXISTS (SELECT 1 FROM public.sms_events e WHERE e.phone_number=j.phone_number
         AND ((e.opt_out IS TRUE AND NOT public.sms_stop_has_reviewed_opt_in(e.id)) OR (e.direction='outbound' AND e.created_at>now()-interval '24 hours'))) THEN
      UPDATE public.retell_form_sms_jobs SET status='stopped',reason='Expired, suppressed, or previous recipient contact' WHERE id=j.id;
      CONTINUE;
    END IF;
    UPDATE public.retell_form_sms_jobs SET status='processing',claimed_at=now() WHERE id=j.id RETURNING * INTO j;
    -- Shared ledger blocks Twilio's claim function from sending alongside Retell.
    INSERT INTO public.sms_events(id,lead_id,provider,direction,phone_number,body,status,raw_payload)
      VALUES(j.id,j.lead_id,CASE WHEN p_transport='retell_native' THEN 'retell' ELSE 'twilio' END,
        'outbound',j.phone_number,coalesce(j.delivery_body,'Retell consented form response pending'),'submitting',
        CASE WHEN p_transport='app_twilio' THEN jsonb_build_object('transport',p_transport,'form_job_id',j.id,'sender_number',j.delivery_sender) ELSE '{}'::jsonb END);
    RETURN NEXT j;
  END LOOP;
END; $function$
;
REVOKE ALL ON FUNCTION public.claim_retell_form_sms_transport(integer,uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_retell_form_sms_transport(integer,uuid,text) TO service_role;


-- Old deployed worker can only claim native jobs; it cannot accidentally send
-- an app-owned inquiry through create-sms-chat.
CREATE OR REPLACE FUNCTION public.claim_retell_form_sms_matching(p_limit integer,p_job uuid)
RETURNS SETOF public.retell_form_sms_jobs LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT * FROM public.claim_retell_form_sms_transport(p_limit,p_job,'retell_native');
$$;
REVOKE ALL ON FUNCTION public.claim_retell_form_sms_matching(integer,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_retell_form_sms_matching(integer,uuid) TO service_role;
CREATE FUNCTION public.claim_retell_app_ack(p_job uuid)
RETURNS SETOF public.retell_form_sms_jobs LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF p_job IS NULL THEN RAISE EXCEPTION 'Exact inquiry required'; END IF;
 RETURN QUERY SELECT * FROM public.claim_retell_form_sms_transport(1,p_job,'app_twilio');
END $$;
REVOKE ALL ON FUNCTION public.claim_retell_app_ack(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_retell_app_ack(uuid) TO service_role;

CREATE TABLE public.retell_api_sessions (
 id uuid PRIMARY KEY REFERENCES public.retell_form_sms_jobs(id),
 lead_id uuid NOT NULL REFERENCES public.leads(id),
 phone_number text NOT NULL,
 sender_number text NOT NULL,
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','creating','ready','review','closed')),
 chat_id text UNIQUE,
 agent_id text,
 agent_version integer CHECK(agent_version BETWEEN 0 AND 999999999),
 created_at timestamptz NOT NULL DEFAULT now(),
 claimed_at timestamptz,
 reason text,
 CHECK((chat_id IS NULL OR chat_id ~ '^[A-Za-z0-9_-]{1,128}$') AND (status<>'ready' OR chat_id IS NOT NULL))
);
CREATE UNIQUE INDEX retell_api_one_recipient ON public.retell_api_sessions(phone_number) WHERE status<>'closed';
CREATE TABLE public.retell_api_turns (
 id uuid PRIMARY KEY REFERENCES public.sms_events(id),
 session_id uuid NOT NULL REFERENCES public.retell_api_sessions(id),
 inbound_sid text NOT NULL UNIQUE CHECK(inbound_sid ~ '^SM[0-9a-fA-F]{32}$'),
 recipient_text text NOT NULL CHECK(length(trim(recipient_text)) BETWEEN 1 AND 1600),
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','creating_session','generating','generated','submitting','accepted','review','stopped')),
 created_at timestamptz NOT NULL DEFAULT now(),
 expires_at timestamptz NOT NULL,
 claimed_at timestamptz,
 generated_messages jsonb,
 outbound_id uuid UNIQUE,
 reason text
);
CREATE INDEX retell_api_turn_order ON public.retell_api_turns(session_id,created_at,id);
ALTER TABLE public.retell_api_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.retell_api_turns ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.retell_api_sessions,public.retell_api_turns FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON public.retell_api_sessions,public.retell_api_turns TO service_role;

-- Consume only the carrier receipt already authenticated/committed by the webhook.
-- No caller-supplied phone, text, SID or expiry can replace that receipt.
CREATE FUNCTION public.enqueue_retell_api_turn(p_job uuid,p_event uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE j public.retell_form_sms_jobs; e public.sms_events; existing public.retell_api_turns; body_control text;
BEGIN
 SELECT * INTO j FROM public.retell_form_sms_jobs WHERE id=p_job;
 IF NOT FOUND OR j.delivery_transport<>'app_twilio' OR j.status<>'accepted' THEN
  RETURN jsonb_build_object('queued',false,'reason','inquiry_not_accepted'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('seller-outreach:'||j.phone_number,0));
 SELECT * INTO e FROM public.sms_events WHERE id=p_event;
 IF NOT FOUND OR e.provider<>'twilio' OR e.direction<>'inbound' OR e.lead_id IS DISTINCT FROM j.lead_id
  OR e.phone_number IS DISTINCT FROM j.phone_number OR e.status IS DISTINCT FROM 'replied'
  OR e.opt_out IS DISTINCT FROM false OR coalesce(e.raw_payload->>'crm_opt_out','true')<>'false'
  OR coalesce(e.raw_payload->>'MessageSid','') !~ '^SM[0-9a-fA-F]{32}$'
  OR e.raw_payload->>'From' IS DISTINCT FROM j.phone_number OR e.raw_payload->>'To' IS DISTINCT FROM j.delivery_sender
  OR e.body IS DISTINCT FROM e.raw_payload->>'Body'
  OR length(trim(coalesce(e.body,''))) NOT BETWEEN 1 AND 1600 THEN
  RETURN jsonb_build_object('queued',false,'reason','carrier_receipt_mismatch'); END IF;
 body_control:=upper(regexp_replace(trim(e.body),'[.!?]+$','','g'));
 IF coalesce(e.raw_payload->>'OptOutType','')<>'' OR body_control IN
  ('STOP','STOPALL','UNSUBSCRIBE','CANCEL','END','QUIT','REVOKE','OPTOUT','OPT OUT','START','UNSTOP','YES','HELP','INFO') THEN
  RETURN jsonb_build_object('queued',false,'reason','carrier_control'); END IF;
 SELECT * INTO existing FROM public.retell_api_turns WHERE id=p_event OR inbound_sid=e.raw_payload->>'MessageSid';
 IF FOUND THEN
  IF existing.id<>p_event OR existing.session_id<>p_job OR existing.recipient_text<>e.body THEN RAISE EXCEPTION 'Inbound turn identity conflict'; END IF;
  RETURN jsonb_build_object('queued',false,'reason','existing_turn','turn_id',existing.id); END IF;
 IF e.created_at<j.created_at OR e.created_at>now()+interval '5 seconds' OR e.created_at<=now()-interval '15 minutes'
  OR coalesce((public.intake_phone_status(j.phone_number,j.lead_id,''))->>'suppressed','true')<>'false'
  OR NOT EXISTS(SELECT 1 FROM public.leads WHERE id=j.lead_id AND dnc IS FALSE AND status NOT IN ('dnc','dead','closed','sold','under_contract'))
  OR NOT EXISTS(SELECT 1 FROM public.sms_events WHERE id=j.id AND provider='twilio' AND direction='outbound'
    AND phone_number=j.phone_number AND lead_id=j.lead_id AND body=j.delivery_body AND created_at<=e.created_at
    AND raw_payload->>'transport'='app_twilio' AND raw_payload->>'form_job_id'=j.id::text
    AND raw_payload->>'sender_number'=j.delivery_sender AND status IN ('accepted','queued','sending','sent','delivered','read')
    AND raw_payload->>'provider_sid' ~ '^SM[0-9a-fA-F]{32}$') THEN
  RETURN jsonb_build_object('queued',false,'reason','expired_suppressed_or_ack_unconfirmed'); END IF;
 IF EXISTS(SELECT 1 FROM public.retell_api_sessions WHERE phone_number=j.phone_number AND id<>j.id AND status<>'closed') THEN
  RETURN jsonb_build_object('queued',false,'reason','other_conversation'); END IF;
 INSERT INTO public.retell_api_sessions(id,lead_id,phone_number,sender_number)
  VALUES(j.id,j.lead_id,j.phone_number,j.delivery_sender) ON CONFLICT(id) DO NOTHING;
 IF NOT EXISTS(SELECT 1 FROM public.retell_api_sessions WHERE id=j.id AND status IN ('pending','creating','ready')
  AND lead_id=j.lead_id AND phone_number=j.phone_number AND sender_number=j.delivery_sender) THEN
  RETURN jsonb_build_object('queued',false,'reason','conversation_held'); END IF;
 INSERT INTO public.retell_api_turns(id,session_id,inbound_sid,recipient_text,created_at,expires_at)
  VALUES(e.id,j.id,e.raw_payload->>'MessageSid',e.body,e.created_at,e.created_at+interval '15 minutes');
 RETURN jsonb_build_object('queued',true,'turn_id',e.id,'session_id',j.id);
END $$;
REVOKE ALL ON FUNCTION public.enqueue_retell_api_turn(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.enqueue_retell_api_turn(uuid,uuid) TO service_role;

-- Only the oldest unfinished turn may acquire a one-shot provider operation.
CREATE FUNCTION public.claim_retell_api_turn(p_turn uuid,p_agent text,p_version integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE t public.retell_api_turns; s public.retell_api_sessions; earliest uuid;
BEGIN
 IF p_turn IS NULL OR coalesce(p_agent,'') !~ '^[A-Za-z0-9_-]{1,128}$' OR p_version IS NULL OR p_version NOT BETWEEN 0 AND 999999999 THEN RAISE EXCEPTION 'Invalid generation claim'; END IF;
 SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn;
 IF NOT FOUND THEN RETURN jsonb_build_object('claimed',false,'reason','missing_turn'); END IF;
 SELECT * INTO s FROM public.retell_api_sessions WHERE id=t.session_id;
 PERFORM pg_advisory_xact_lock(hashtextextended('seller-outreach:'||s.phone_number,0));
 SELECT * INTO s FROM public.retell_api_sessions WHERE id=t.session_id FOR UPDATE;
 SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn FOR UPDATE;
 IF t.status<>'queued' OR s.status NOT IN ('pending','ready') THEN RETURN jsonb_build_object('claimed',false,'reason','already_claimed_or_held'); END IF;
 SELECT id INTO earliest FROM public.retell_api_turns WHERE session_id=s.id AND status NOT IN ('accepted','stopped') ORDER BY created_at,id LIMIT 1;
 IF earliest IS DISTINCT FROM t.id THEN RETURN jsonb_build_object('claimed',false,'reason','previous_turn_unfinished'); END IF;
 IF t.expires_at<=now() OR coalesce((public.intake_phone_status(s.phone_number,s.lead_id,''))->>'suppressed','true')<>'false'
  OR NOT EXISTS(SELECT 1 FROM public.leads WHERE id=s.lead_id AND dnc IS FALSE AND status NOT IN ('dnc','dead','closed','sold','under_contract')) THEN
  UPDATE public.retell_api_turns SET status='stopped',reason='Expired or suppressed before generation' WHERE id=t.id;
  RETURN jsonb_build_object('claimed',false,'reason','expired_or_suppressed'); END IF;
 IF s.status='ready' AND (s.agent_id IS DISTINCT FROM p_agent OR s.agent_version IS DISTINCT FROM p_version) THEN
  RETURN jsonb_build_object('claimed',false,'reason','session_release_mismatch'); END IF;
 UPDATE public.retell_api_turns SET status=CASE WHEN s.status='pending' THEN 'creating_session' ELSE 'generating' END,claimed_at=now() WHERE id=t.id;
 IF s.status='pending' THEN
  UPDATE public.retell_api_sessions SET status='creating',agent_id=p_agent,agent_version=p_version,claimed_at=now() WHERE id=s.id;
 END IF;
 RETURN jsonb_build_object('claimed',true,'create_session',s.status='pending','session_id',s.id,
  'chat_id',s.chat_id,'lead_id',s.lead_id,'turn_id',t.id,'recipient_text',t.recipient_text,'expires_at',t.expires_at);
END $$;
REVOKE ALL ON FUNCTION public.claim_retell_api_turn(uuid,text,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_retell_api_turn(uuid,text,integer) TO service_role;

-- The worker has verified the provider's exact API-chat receipt before this RPC.
-- A lost response to this RPC can be read/reconciled, never recreate the chat.
CREATE FUNCTION public.bind_retell_api_session(p_turn uuid,p_chat text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE t public.retell_api_turns; s public.retell_api_sessions;
BEGIN
 IF coalesce(p_chat,'') !~ '^[A-Za-z0-9_-]{1,128}$' THEN RAISE EXCEPTION 'Invalid API chat identity'; END IF;
 SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn;
 IF NOT FOUND THEN RAISE EXCEPTION 'Missing turn'; END IF;
 SELECT * INTO s FROM public.retell_api_sessions WHERE id=t.session_id FOR UPDATE;
 SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn FOR UPDATE;
 IF s.status='ready' AND s.chat_id=p_chat AND t.status='generating' THEN RETURN jsonb_build_object('bound',true,'replayed',true); END IF;
 IF s.status<>'creating' OR s.chat_id IS NOT NULL OR t.status<>'creating_session' THEN RAISE EXCEPTION 'Session binding conflict'; END IF;
 UPDATE public.retell_api_sessions SET chat_id=p_chat,status='ready' WHERE id=s.id;
 UPDATE public.retell_api_turns SET status='generating' WHERE id=t.id;
 RETURN jsonb_build_object('bound',true,'replayed',false);
END $$;
REVOKE ALL ON FUNCTION public.bind_retell_api_session(uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.bind_retell_api_session(uuid,text) TO service_role;

CREATE FUNCTION public.save_retell_api_generation(p_turn uuid,p_messages jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE t public.retell_api_turns; s public.retell_api_sessions; m jsonb; total integer:=0;
BEGIN
 IF jsonb_typeof(p_messages) IS DISTINCT FROM 'array' OR jsonb_array_length(p_messages) NOT BETWEEN 1 AND 20 THEN RAISE EXCEPTION 'Invalid generated turn'; END IF;
 FOR m IN SELECT value FROM jsonb_array_elements(p_messages) LOOP
  IF jsonb_typeof(m) IS DISTINCT FROM 'object' OR (SELECT count(*) FROM jsonb_object_keys(m))<>2
   OR NOT(m ?& ARRAY['message_id','content']) OR jsonb_typeof(m->'message_id') IS DISTINCT FROM 'string' OR coalesce(m->>'message_id','') !~ '^[A-Za-z0-9_-]{1,128}$'
   OR jsonb_typeof(m->'content') IS DISTINCT FROM 'string' OR length(trim(m->>'content')) NOT BETWEEN 1 AND 1600 THEN RAISE EXCEPTION 'Invalid generated message'; END IF;
  total:=total+length(m->>'content')+1;
 END LOOP;
 IF total-1>1600 OR (SELECT count(DISTINCT value->>'message_id') FROM jsonb_array_elements(p_messages))<>jsonb_array_length(p_messages) THEN RAISE EXCEPTION 'Ambiguous or oversized generated turn'; END IF;
 SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn;
 IF NOT FOUND THEN RAISE EXCEPTION 'Missing turn'; END IF;
 SELECT * INTO s FROM public.retell_api_sessions WHERE id=t.session_id FOR UPDATE;
 SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn FOR UPDATE;
 IF t.generated_messages=p_messages AND t.status IN ('generated','submitting','accepted') THEN RETURN jsonb_build_object('saved',true,'replayed',true); END IF;
 IF t.status<>'generating' OR s.status<>'ready' OR t.generated_messages IS NOT NULL THEN RAISE EXCEPTION 'Generation receipt conflict'; END IF;
 UPDATE public.retell_api_turns SET generated_messages=p_messages,status='generated' WHERE id=t.id;
 RETURN jsonb_build_object('saved',true,'replayed',false,'dispatch_authorized',false);
END $$;
REVOKE ALL ON FUNCTION public.save_retell_api_generation(uuid,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.save_retell_api_generation(uuid,jsonb) TO service_role;

-- Park a particular one-shot operation. Never reset it to queued or replay it.
CREATE FUNCTION public.hold_retell_api_turn(p_turn uuid,p_expected text,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE t public.retell_api_turns; s public.retell_api_sessions;
BEGIN
 IF p_expected IS NULL OR p_expected NOT IN ('creating_session','generating','generated','submitting')
  OR length(trim(coalesce(p_reason,''))) NOT BETWEEN 1 AND 500 THEN RAISE EXCEPTION 'Invalid operation hold'; END IF;
 SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn;
 IF NOT FOUND THEN RETURN jsonb_build_object('held',false); END IF;
 SELECT * INTO s FROM public.retell_api_sessions WHERE id=t.session_id FOR UPDATE;
 SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn FOR UPDATE;
 IF t.status<>p_expected THEN RETURN jsonb_build_object('held',false); END IF;
 UPDATE public.retell_api_turns SET status='review',reason=p_reason WHERE id=t.id;
 UPDATE public.retell_api_sessions SET status='review',reason=p_reason WHERE id=s.id AND status<>'closed';
 RETURN jsonb_build_object('held',true,'dispatch_authorized',false);
END $$;
REVOKE ALL ON FUNCTION public.hold_retell_api_turn(uuid,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.hold_retell_api_turn(uuid,text,text) TO service_role;

-- Preserve exact carrier input and one-shot operation history even if a later
-- service-side upsert accidentally includes mutable identity fields.
CREATE FUNCTION public.protect_retell_api_turn() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF ROW(NEW.id,NEW.session_id,NEW.inbound_sid,NEW.recipient_text,NEW.created_at,NEW.expires_at)
  IS DISTINCT FROM ROW(OLD.id,OLD.session_id,OLD.inbound_sid,OLD.recipient_text,OLD.created_at,OLD.expires_at)
  OR (OLD.generated_messages IS NOT NULL AND NEW.generated_messages IS DISTINCT FROM OLD.generated_messages)
  OR (OLD.outbound_id IS NOT NULL AND NEW.outbound_id IS DISTINCT FROM OLD.outbound_id)
  OR (NEW.status<>OLD.status AND NOT (
   (OLD.status='queued' AND NEW.status IN ('creating_session','generating','stopped')) OR
   (OLD.status='creating_session' AND NEW.status IN ('generating','review')) OR
   (OLD.status='generating' AND NEW.status IN ('generated','review')) OR
   (OLD.status='generated' AND NEW.status IN ('submitting','review','stopped')) OR
   (OLD.status='submitting' AND NEW.status IN ('accepted','review')) OR
   (OLD.status='accepted' AND NEW.status='review') OR
   (OLD.status='review' AND NEW.status='stopped')
  )) THEN RAISE EXCEPTION 'Turn identity, evidence or one-shot state is immutable'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.protect_retell_api_turn() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER protect_retell_api_turn BEFORE UPDATE ON public.retell_api_turns
 FOR EACH ROW EXECUTE FUNCTION public.protect_retell_api_turn();
CREATE FUNCTION public.protect_retell_api_session() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF ROW(NEW.id,NEW.lead_id,NEW.phone_number,NEW.sender_number,NEW.created_at)
  IS DISTINCT FROM ROW(OLD.id,OLD.lead_id,OLD.phone_number,OLD.sender_number,OLD.created_at)
  OR (OLD.chat_id IS NOT NULL AND NEW.chat_id IS DISTINCT FROM OLD.chat_id)
  OR (OLD.agent_id IS NOT NULL AND ROW(NEW.agent_id,NEW.agent_version) IS DISTINCT FROM ROW(OLD.agent_id,OLD.agent_version))
  OR (NEW.status<>OLD.status AND NOT (
   (OLD.status='pending' AND NEW.status IN ('creating','closed')) OR
   (OLD.status='creating' AND NEW.status IN ('ready','review')) OR
   (OLD.status='ready' AND NEW.status IN ('review','closed')) OR
   (OLD.status='review' AND NEW.status='closed')
  )) THEN RAISE EXCEPTION 'Session identity or one-shot state is immutable'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.protect_retell_api_session() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER protect_retell_api_session BEFORE UPDATE ON public.retell_api_sessions
 FOR EACH ROW EXECUTE FUNCTION public.protect_retell_api_session();
