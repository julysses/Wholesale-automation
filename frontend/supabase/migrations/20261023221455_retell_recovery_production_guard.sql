-- Match the production baseline: empty-session recovery was never deployed.
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
   ))
  )) THEN RAISE EXCEPTION 'Session identity or one-shot state is immutable'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.protect_retell_api_session() FROM PUBLIC,anon,authenticated;

