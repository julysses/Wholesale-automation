-- Operator-only recovery from a fresh authenticated GET and archived signed event.
-- No generation, network request, expiry extension, or delivery occurs here.
CREATE TABLE private.retell_generation_reconciliations (
 turn_id uuid PRIMARY KEY REFERENCES public.retell_api_turns(id),
 session_id uuid NOT NULL REFERENCES public.retell_api_sessions(id),
 request_id bigint NOT NULL UNIQUE, event_id uuid NOT NULL UNIQUE,
 messages jsonb NOT NULL, before_state jsonb NOT NULL, proof jsonb NOT NULL,
 note text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), applied_at timestamptz
);
ALTER TABLE private.retell_generation_reconciliations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.retell_generation_reconciliations FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON private.retell_generation_reconciliations TO service_role;
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
     SELECT 1 FROM private.retell_generation_reconciliations r
     JOIN public.retell_api_turns t ON t.id=r.turn_id
     WHERE r.session_id=NEW.id AND r.applied_at IS NULL AND r.created_at>=now()-interval '1 minute'
       AND t.session_id=NEW.id AND t.status='review' AND t.generated_messages IS NULL AND t.outbound_id IS NULL
   )) OR
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

CREATE OR REPLACE FUNCTION public.protect_retell_api_turn() RETURNS trigger
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
   (OLD.status='review' AND NEW.status='stopped') OR
   (OLD.status='review' AND NEW.status='generated' AND OLD.generated_messages IS NULL
     AND OLD.outbound_id IS NULL AND NEW.outbound_id IS NULL AND EXISTS(
       SELECT 1 FROM private.retell_generation_reconciliations r WHERE r.turn_id=NEW.id
       AND r.session_id=NEW.session_id AND r.messages=NEW.generated_messages
       AND r.applied_at IS NULL AND r.created_at>=now()-interval '1 minute'))
  )) THEN RAISE EXCEPTION 'Turn identity, evidence or one-shot state is immutable'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.protect_retell_api_turn() FROM PUBLIC,anon,authenticated;

CREATE FUNCTION private.reconcile_retell_generation(p_turn uuid,p_request bigint,p_event uuid,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE t public.retell_api_turns; s public.retell_api_sessions; proof jsonb; payload jsonb;
 history jsonb; candidate jsonb; messages jsonb;
BEGIN
 IF length(trim(coalesce(p_note,''))) NOT BETWEEN 20 AND 1000 THEN RAISE EXCEPTION 'Operator note required'; END IF;
 SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn;
 IF NOT FOUND THEN RAISE EXCEPTION 'Missing exact turn'; END IF;
 SELECT * INTO s FROM public.retell_api_sessions WHERE id=t.session_id;
 PERFORM pg_advisory_xact_lock(hashtextextended('seller-outreach:'||s.phone_number,0));
 PERFORM 1 FROM public.retell_form_sms_jobs WHERE id=s.id FOR UPDATE;
 SELECT * INTO s FROM public.retell_api_sessions WHERE id=t.session_id FOR UPDATE;
 SELECT * INTO t FROM public.retell_api_turns WHERE id=p_turn FOR UPDATE;
 IF s.status<>'review' OR t.status<>'review' OR t.generated_messages IS NOT NULL OR t.outbound_id IS NOT NULL
  OR s.chat_id IS NULL OR t.expires_at<=now()
  OR EXISTS(SELECT 1 FROM private.retell_generation_reconciliations WHERE turn_id=t.id)
  OR (SELECT count(*) FROM public.retell_api_turns WHERE session_id=s.id)<>1
  OR EXISTS(SELECT 1 FROM public.sms_events WHERE raw_payload->>'api_turn_id'=t.id::text)
  OR NOT EXISTS(SELECT 1 FROM public.retell_form_sms_jobs WHERE id=s.id AND status='accepted' AND delivery_transport='app_twilio')
  OR NOT EXISTS(SELECT 1 FROM public.sms_events WHERE id=s.id AND status IN ('delivered','read'))
  OR NOT EXISTS(SELECT 1 FROM public.leads WHERE id=s.lead_id AND dnc IS FALSE AND status NOT IN ('dnc','dead','closed','sold','under_contract'))
  OR coalesce(public.intake_phone_status(s.phone_number,s.lead_id,'')->>'suppressed','true')<>'false'
 THEN RAISE EXCEPTION 'Turn has unresolved, expired, suppressed or non-first-turn evidence'; END IF;
 SELECT content::jsonb INTO proof FROM net._http_response WHERE id=p_request AND status_code=200
   AND timed_out IS FALSE AND created>=now()-interval '5 minutes';
 IF proof IS NULL OR proof->>'status' IS DISTINCT FROM 'inspected'
  OR proof->'dispatch_authorized' IS DISTINCT FROM 'false'::jsonb
  OR proof->>'session_id' IS DISTINCT FROM s.id::text OR proof->>'chat_id' IS DISTINCT FROM s.chat_id
  OR NOT coalesce(proof->'checks' @> '{"chat_id":true,"chat_type":true,"agent_id":true,"metadata":true,"ongoing":true,"pinned_version_valid":true}'::jsonb,false)
  OR jsonb_typeof(proof->'first_turn_proof') IS DISTINCT FROM 'object'
 THEN RAISE EXCEPTION 'Fresh authenticated first-turn inspection required'; END IF;
 SELECT w.payload INTO payload FROM public.webhook_jobs w WHERE id=p_event AND source='retell_api_chat' AND status='done';
 IF payload IS NULL OR payload->>'event' IS DISTINCT FROM 'transcript_updated'
  OR payload->'chat'->>'chat_id' IS DISTINCT FROM s.chat_id
  OR payload->'chat'->>'chat_type' IS DISTINCT FROM 'api_chat'
  OR payload->'chat'->>'agent_id' IS DISTINCT FROM s.agent_id
  OR payload->'chat'->'agent_version' IS DISTINCT FROM to_jsonb(s.agent_version)
  OR payload->'chat'->'metadata' IS DISTINCT FROM jsonb_build_object('operation_id',s.id,'lead_id',s.lead_id,'transport','wholesaleos_twilio')
 THEN RAISE EXCEPTION 'Authenticated event identity mismatch'; END IF;
 history:=payload->'transcript_with_tool_calls'; candidate:=history->1;
 IF jsonb_typeof(history) IS DISTINCT FROM 'array' OR jsonb_array_length(history)<>2
  OR history->0->>'role' IS DISTINCT FROM 'user' OR history->0->>'content' IS DISTINCT FROM t.recipient_text
  OR candidate->>'role' IS DISTINCT FROM 'agent'
  OR jsonb_typeof(candidate->'content') IS DISTINCT FROM 'string'
  OR length(trim(candidate->>'content')) NOT BETWEEN 1 AND 99
  OR candidate->>'content' ~ '[[:cntrl:]]'
  OR coalesce(candidate->>'message_id','') !~ '^[A-Za-z0-9_-]{1,128}$'
  OR candidate->>'message_id'=history->0->>'message_id'
  OR (candidate ? 'multimedia' AND candidate->'multimedia' NOT IN ('null'::jsonb,'[]'::jsonb))
  OR proof->'first_turn_proof' IS DISTINCT FROM jsonb_build_object(
   'user_message_id',history->0->>'message_id',
   'recipient_sha256',encode(sha256(convert_to(t.recipient_text,'UTF8')),'hex'),
   'message_id',candidate->>'message_id',
   'content_sha256',encode(sha256(convert_to(candidate->>'content','UTF8')),'hex'))
 THEN RAISE EXCEPTION 'Transcript is ambiguous, unsafe or does not match live proof'; END IF;
 messages:=jsonb_build_array(jsonb_build_object('message_id',candidate->>'message_id','content',candidate->>'content'));
 INSERT INTO private.retell_generation_reconciliations(turn_id,session_id,request_id,event_id,messages,before_state,proof,note)
 VALUES(t.id,s.id,p_request,p_event,messages,jsonb_build_object('turn',to_jsonb(t),'session',to_jsonb(s)),proof,p_note);
 UPDATE public.retell_api_sessions SET status='ready',reason='Existing generated reply verified; no completion replay' WHERE id=s.id;
 UPDATE public.retell_api_turns SET status='generated',generated_messages=messages,
  reason='Existing provider reply verified against signed event and fresh GET; no regeneration' WHERE id=t.id;
 UPDATE private.retell_generation_reconciliations SET applied_at=now() WHERE turn_id=t.id;
 RETURN jsonb_build_object('reconciled',true,'turn_id',t.id,'dispatch_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.reconcile_retell_generation(uuid,bigint,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
