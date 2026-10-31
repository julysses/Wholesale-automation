-- Local proposal only. Bounded discovery is not upload, verification or approval authority.
-- Compensation: keep acquisition activation disabled; preserve registry and version history.
BEGIN;
CREATE FUNCTION private.contract_document_candidates(p_workspace uuid,p_contract uuid,p_version integer,p_purpose text,p_after uuid,p_limit integer)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE policy jsonb; items jsonb; candidate record; next_after uuid; last_id uuid; seen integer:=0;
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2' OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Evidence discovery authority required' USING ERRCODE='42501'; END IF;
 IF p_version IS NULL OR p_version<1 OR p_purpose IS NULL OR p_purpose NOT IN ('purchase_contract','title_report','assignment_agreement','seller_disclosure','assignee_disclosure','closing_statement','supporting_document') OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 THEN
  RAISE EXCEPTION 'Bounded evidence purpose and page required' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM public.acquisition_contract_versions WHERE workspace_id=p_workspace AND deal_id=p_contract AND version=p_version;
 IF NOT FOUND THEN RAISE EXCEPTION 'Contract version unavailable' USING ERRCODE='42501'; END IF;
 -- Discovery works while activation is paused and for historical contract versions. Registration rechecks all write gates.
 SELECT jsonb_build_object('id',id,'workspace_id',workspace_id,'purpose',purpose,'version',version,'retention_seconds',retention_seconds,'valid_from',valid_from,'valid_until',valid_until)
 INTO policy FROM private.acquisition_evidence_policies WHERE workspace_id=p_workspace AND purpose=p_purpose
  AND revoked_at IS NULL AND valid_from<=statement_timestamp() AND valid_until>statement_timestamp()
 ORDER BY version DESC LIMIT 1;
 items:='[]'::jsonb;
 FOR candidate IN SELECT id FROM public.acquisition_evidence_artifacts
  WHERE workspace_id=p_workspace AND campaign_id IS NULL AND contract_id=p_contract AND contract_version=p_version AND purpose=p_purpose AND (p_after IS NULL OR id>p_after)
  ORDER BY id LIMIT p_limit+1 LOOP
  seen:=seen+1;
  IF seen>p_limit THEN next_after:=last_id; EXIT; END IF;
  items:=items||jsonb_build_array(private.contract_document_state(p_workspace,p_contract,p_version,candidate.id));
  last_id:=candidate.id;
 END LOOP;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'purpose',p_purpose,
  'current_policy',policy,'items',items,'next_after',next_after,'checked_at',statement_timestamp(),'execution_authorized',false);
END $$;
CREATE FUNCTION public.contract_document_candidates(p_workspace uuid,p_contract uuid,p_version integer,p_purpose text,p_after uuid,p_limit integer)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.contract_document_candidates(p_workspace,p_contract,p_version,p_purpose,p_after,p_limit)
$$;
REVOKE ALL ON FUNCTION private.contract_document_candidates(uuid,uuid,integer,text,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.contract_document_candidates(uuid,uuid,integer,text,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.contract_document_candidates(uuid,uuid,integer,text,uuid,integer) TO authenticated;
GRANT EXECUTE ON FUNCTION public.contract_document_candidates(uuid,uuid,integer,text,uuid,integer) TO authenticated;
COMMIT;
