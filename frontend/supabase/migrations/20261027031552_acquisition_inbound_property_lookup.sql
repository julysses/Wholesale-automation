-- Call-scoped lookup of the current saved intake; never disclose owner records.
BEGIN;
CREATE FUNCTION private.acquisition_inbound_property_lookup(p_integration uuid,p_number text,p_agent text,
 p_agent_version integer,p_call text,p_intake_revision integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE route private.acquisition_inbound_routes%ROWTYPE; intake public.seller_intakes%ROWTYPE;
 answers jsonb; v_street text; v_city text; v_state text; matches integer; result_status text;
BEGIN
 PERFORM 1 FROM private.acquisition_activation WHERE singleton AND enabled FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM private.acquisition_integrations WHERE id=p_integration AND provider='retell' AND enabled FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Inbound integration unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO route FROM private.acquisition_inbound_routes WHERE integration_id=p_integration AND enabled FOR SHARE;
 IF NOT FOUND OR route.acquisition_number IS DISTINCT FROM p_number OR route.agent_id IS DISTINCT FROM p_agent
  OR route.agent_version IS DISTINCT FROM p_agent_version THEN RAISE EXCEPTION 'Inbound route unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=route.workspace_id AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 IF p_call IS NULL OR p_call !~ '^[A-Za-z0-9_-]{1,200}$' OR p_intake_revision IS NULL
  OR p_intake_revision NOT BETWEEN 1 AND 1000000000 THEN
  RAISE EXCEPTION 'Invalid lookup context' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-inbound:'||p_integration::text||':'||p_call,0));
 IF NOT EXISTS(SELECT 1 FROM public.call_events WHERE acquisition_integration_id=p_integration
  AND acquisition_call_id=p_call AND acquisition_event_type='call_started' AND acquisition_projection->>'call_status'='ongoing')
  OR EXISTS(SELECT 1 FROM public.call_events WHERE acquisition_integration_id=p_integration
   AND acquisition_call_id=p_call AND acquisition_event_type IN ('call_ended','call_analyzed')) THEN
  RAISE EXCEPTION 'Ongoing inbound ledger required' USING ERRCODE='55000'; END IF;
 SELECT * INTO intake FROM public.seller_intakes WHERE workspace_id=route.workspace_id
  AND inbound_integration_id=p_integration AND inbound_call_id=p_call ORDER BY inbound_revision DESC LIMIT 1;
 IF NOT FOUND OR intake.inbound_revision<>p_intake_revision THEN
  RAISE EXCEPTION 'Current saved intake required' USING ERRCODE='40001'; END IF;
 answers:=intake.prepared_answers->'answers';
 v_street:=private.acquisition_identity_text(answers->>'property_address');
 v_city:=private.acquisition_identity_text(answers->>'city');
 v_state:=private.acquisition_identity_text(answers->>'state');
 IF v_state='texas' THEN v_state:='tx'; END IF;
 IF v_street IS NULL OR v_city IS NULL OR v_state IS NULL THEN result_status:='incomplete_address';
 ELSE
  -- Only enrolled canonical county properties; no contact/owner match, fuzzy
  -- expansion, prefix search, private lead data or automatic association.
  SELECT count(*) INTO matches FROM (
   SELECT p.id FROM public.workspace_leads b JOIN wholesale_ingest.properties p
    ON p.id=b.property_id AND p.lead_id=b.lead_id
   WHERE b.workspace_id=route.workspace_id AND b.lead_id<>intake.lead_id
    AND private.acquisition_identity_text(p.address_std)=v_street
    AND private.acquisition_identity_text(p.city)=v_city
    AND (CASE WHEN private.acquisition_identity_text(p.state)='texas' THEN 'tx'
      ELSE private.acquisition_identity_text(p.state) END)=v_state
   LIMIT 2
  ) bounded;
  result_status:=CASE WHEN matches=0 THEN 'no_address_candidate' WHEN matches=1 THEN 'address_candidate' ELSE 'multiple_address_candidates' END;
 END IF;
 RETURN jsonb_build_object('workspace_id',route.workspace_id,'integration_id',p_integration,'call_id',p_call,
  'intake_revision',intake.inbound_revision,'status',result_status,'policy_version','inbound-property-lookup-v1',
  'review_required',true,'property_verified',false,'ownership_verified',false,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.acquisition_inbound_property_lookup(uuid,text,text,integer,text,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_inbound_property_lookup(uuid,text,text,integer,text,integer) TO service_role;
CREATE FUNCTION public.acquisition_inbound_property_lookup(p_integration uuid,p_number text,p_agent text,
 p_agent_version integer,p_call text,p_intake_revision integer)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.acquisition_inbound_property_lookup(p_integration,p_number,p_agent,p_agent_version,p_call,p_intake_revision)
$$;
REVOKE ALL ON FUNCTION public.acquisition_inbound_property_lookup(uuid,text,text,integer,text,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.acquisition_inbound_property_lookup(uuid,text,text,integer,text,integer) TO service_role;
COMMIT;
