-- Do not infer historic agent versions from current configuration.
ALTER TABLE public.retell_call_requests
 ADD COLUMN requested_agent_id text,
 ADD COLUMN requested_agent_version integer CHECK(requested_agent_version>=0),
 ADD COLUMN requested_from_number text;
CREATE FUNCTION public.protect_retell_claim_identity() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF ROW(NEW.id,NEW.lead_id,NEW.requested_by,NEW.phone_number,NEW.requested_agent_id,NEW.requested_agent_version,NEW.requested_from_number)
 IS DISTINCT FROM ROW(OLD.id,OLD.lead_id,OLD.requested_by,OLD.phone_number,OLD.requested_agent_id,OLD.requested_agent_version,OLD.requested_from_number)
 THEN RAISE EXCEPTION 'Retell initiation identity is immutable'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION public.protect_retell_claim_identity() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER retell_claim_identity_immutable BEFORE UPDATE ON public.retell_call_requests
 FOR EACH ROW EXECUTE FUNCTION public.protect_retell_claim_identity();
CREATE FUNCTION public.claim_retell_call_versioned(p_id uuid,p_lead uuid,p_phone text,p_operator uuid,p_agent text,p_version integer,p_from text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v_id uuid; v_reason text;
BEGIN
  IF coalesce(p_agent,'') !~ '^[A-Za-z0-9_-]{1,255}$' OR p_version IS NULL OR p_version<0
    OR coalesce(p_from,'') !~ '^\+1[2-9][0-9]{9}$' THEN RAISE EXCEPTION 'Invalid Retell identity'; END IF;
  IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved' AND role='admin')
    THEN RAISE EXCEPTION 'Approved administrator required'; END IF;
  IF coalesce(p_phone,'') !~ '^\+1[2-9][0-9]{9}$' THEN RAISE EXCEPTION 'Invalid call phone'; END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('seller-outreach:'||p_phone,0));
  IF EXISTS(SELECT 1 FROM public.retell_call_requests WHERE id=p_id) THEN
    RETURN jsonb_build_object('claimed',false,'reason','existing_reference');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.leads WHERE id=p_lead AND dnc IS FALSE AND ai_calling_paused IS FALSE)
    OR coalesce((public.intake_phone_status(p_phone,p_lead,''))->>'suppressed','true')<>'false' THEN
    RETURN jsonb_build_object('claimed',false,'reason','suppressed_or_paused');
  END IF;
  v_reason:=public.outreach_recipient_limits(p_phone)->>'blocker';
  IF v_reason IS NOT NULL THEN RETURN jsonb_build_object('claimed',false,'reason',v_reason); END IF;
  INSERT INTO public.retell_call_requests(id,lead_id,phone_number,requested_by,status,requested_agent_id,requested_agent_version,requested_from_number)
    VALUES(p_id,p_lead,p_phone,p_operator,'submitting',p_agent,p_version,p_from) ON CONFLICT(id) DO NOTHING RETURNING id INTO v_id;
  RETURN jsonb_build_object('claimed',v_id IS NOT NULL,'reason',CASE WHEN v_id IS NULL THEN 'existing_reference' ELSE 'claimed' END);
END; $$;
REVOKE ALL ON FUNCTION public.claim_retell_call_versioned(uuid,uuid,text,uuid,text,integer,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_retell_call_versioned(uuid,uuid,text,uuid,text,integer,text) TO service_role;

-- Old initiation cannot create an unversioned claim after this release.
REVOKE EXECUTE ON FUNCTION public.claim_retell_call(uuid,uuid,text,uuid) FROM service_role;
