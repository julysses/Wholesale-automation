-- Operator-only recovery of an empty provider chat. Never replay an old turn.
CREATE TABLE private.retell_empty_session_reconciliations(
 session_id uuid PRIMARY KEY REFERENCES public.retell_api_sessions(id),
 chat_id text NOT NULL UNIQUE,agent_id text NOT NULL,agent_version integer NOT NULL,
 request_id bigint NOT NULL UNIQUE,proof jsonb NOT NULL,
 previous_session_reason text,previous_turns jsonb NOT NULL,note text NOT NULL,
 reconciled_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE private.retell_empty_session_reconciliations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.retell_empty_session_reconciliations FROM PUBLIC,anon,authenticated,service_role;
-- The existing invoker state guard reads proof, but application roles cannot create it.
GRANT SELECT ON private.retell_empty_session_reconciliations TO service_role;

CREATE OR REPLACE FUNCTION public.protect_retell_api_session() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF ROW(NEW.id,NEW.lead_id,NEW.phone_number,NEW.sender_number,NEW.created_at)
  IS DISTINCT FROM ROW(OLD.id,OLD.lead_id,OLD.phone_number,OLD.sender_number,OLD.created_at)
  OR (OLD.chat_id IS NOT NULL AND NEW.chat_id IS DISTINCT FROM OLD.chat_id)
  OR (OLD.agent_id IS NOT NULL AND ROW(NEW.agent_id,NEW.agent_version) IS DISTINCT FROM ROW(OLD.agent_id,OLD.agent_version))
  OR (NEW.status<>OLD.status AND NOT (
   (OLD.status='pending' AND NEW.status IN ('creating','review','closed')) OR
   (OLD.status='creating' AND NEW.status IN ('ready','review')) OR
   (OLD.status='ready' AND NEW.status IN ('review','closed')) OR
   (OLD.status='review' AND NEW.status='closed') OR
   (OLD.status='review' AND NEW.status='ready' AND EXISTS(
     SELECT 1 FROM private.retell_empty_session_reconciliations r
     WHERE r.session_id=NEW.id AND r.chat_id=NEW.chat_id
       AND r.agent_id=NEW.agent_id AND r.agent_version=NEW.agent_version
       AND r.reconciled_at>=now()-interval '1 minute'
       AND NOT EXISTS(SELECT 1 FROM public.retell_api_turns t WHERE t.session_id=NEW.id
         AND NOT EXISTS(SELECT 1 FROM jsonb_array_elements(r.previous_turns) x WHERE x->>'id'=t.id::text))
   ) AND NOT EXISTS(SELECT 1 FROM public.retell_api_turns t
       WHERE t.session_id=NEW.id AND t.status<>'stopped'))
  )) THEN RAISE EXCEPTION 'Session identity or one-shot state is immutable'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.protect_retell_api_session() FROM PUBLIC,anon,authenticated;

CREATE FUNCTION private.reconcile_empty_retell_session(p_session uuid,p_chat text,p_request bigint,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE s public.retell_api_sessions; proof jsonb; prior jsonb; stopped_count integer;
BEGIN
 IF p_session IS NULL OR p_chat IS NULL OR p_chat !~ '^[A-Za-z0-9_-]{1,128}$'
  OR p_request IS NULL OR length(trim(coalesce(p_note,''))) NOT BETWEEN 20 AND 1000 THEN
  RAISE EXCEPTION 'Exact session, provider receipt and reconciliation note required'; END IF;
 SELECT * INTO s FROM public.retell_api_sessions WHERE id=p_session;
 IF NOT FOUND THEN RAISE EXCEPTION 'Session not found'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('seller-outreach:'||s.phone_number,0));
 PERFORM 1 FROM public.retell_form_sms_jobs WHERE id=p_session FOR UPDATE;
 SELECT * INTO s FROM public.retell_api_sessions WHERE id=p_session FOR UPDATE;
 PERFORM 1 FROM public.retell_api_turns WHERE session_id=p_session ORDER BY id FOR UPDATE;
 IF s.status<>'review' OR s.chat_id IS NOT NULL OR s.agent_id IS NULL OR s.agent_version IS NULL
  OR EXISTS(SELECT 1 FROM private.retell_empty_session_reconciliations WHERE session_id=p_session)
  OR NOT EXISTS(SELECT 1 FROM public.retell_form_sms_jobs WHERE id=p_session AND status='accepted' AND delivery_transport='app_twilio')
  OR EXISTS(SELECT 1 FROM public.retell_api_turns WHERE session_id=p_session
       AND (status NOT IN ('review','stopped') OR generated_messages IS NOT NULL OR outbound_id IS NOT NULL))
  OR NOT EXISTS(SELECT 1 FROM public.retell_api_turns WHERE session_id=p_session AND status='review') THEN
  RAISE EXCEPTION 'Session has unresolved generation, delivery, or state evidence'; END IF;
 SELECT content::jsonb INTO proof FROM net._http_response WHERE id=p_request AND status_code=200
   AND timed_out IS FALSE AND created>=now()-interval '5 minutes';
 IF proof IS NULL OR proof->>'status' IS DISTINCT FROM 'inspected'
   OR proof->'dispatch_authorized' IS DISTINCT FROM 'false'::jsonb
   OR proof->>'session_id' IS DISTINCT FROM p_session::text OR proof->>'chat_id' IS DISTINCT FROM p_chat
   OR NOT coalesce((proof->'checks') @> '{"chat_id":true,"chat_type":true,"agent_id":true,"metadata":true,"ongoing":true,"pinned_version_valid":true}'::jsonb,false)
   OR jsonb_typeof(proof->'history_shape') IS DISTINCT FROM 'object' THEN
  RAISE EXCEPTION 'Fresh authenticated identity and version evidence required'; END IF;
 IF NOT EXISTS(SELECT 1 FROM jsonb_each(proof->'history_shape') h
      WHERE h.key IN ('message_with_tool_calls','transcript_with_tool_calls','messages')
      AND h.value='{"type":"list","empty":true}'::jsonb)
   OR EXISTS(SELECT 1 FROM jsonb_each(proof->'history_shape') h
      WHERE h.key NOT IN ('transcript','message_with_tool_calls','transcript_with_tool_calls','messages')
        OR h.value->'empty' IS DISTINCT FROM 'true'::jsonb
        OR h.value->>'type' NOT IN ('str','list')) THEN
  RAISE EXCEPTION 'Provider conversation is not proven empty'; END IF;
 SELECT jsonb_agg(jsonb_build_object('id',id,'status',status,'reason',reason) ORDER BY id)
 INTO prior FROM public.retell_api_turns WHERE session_id=p_session;
 INSERT INTO private.retell_empty_session_reconciliations
 (session_id,chat_id,agent_id,agent_version,request_id,proof,previous_session_reason,previous_turns,note)
 VALUES(s.id,p_chat,s.agent_id,s.agent_version,p_request,proof,s.reason,prior,p_note);
 UPDATE public.retell_api_turns SET status='stopped',reason='Stopped after empty-chat reconciliation; original reason retained in audit; never replay'
 WHERE session_id=p_session AND status='review';
 GET DIAGNOSTICS stopped_count=ROW_COUNT;
 UPDATE public.retell_api_sessions SET chat_id=p_chat,status='ready',
 reason='Empty provider chat verified; previous turn stopped; awaiting fresh carrier input'
 WHERE id=p_session;
 RETURN jsonb_build_object('reconciled',true,'stopped_turns',stopped_count,'dispatch_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.reconcile_empty_retell_session(uuid,text,bigint,text) FROM PUBLIC,anon,authenticated,service_role;
