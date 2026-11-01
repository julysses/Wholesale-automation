-- Bounded source-reference discovery for the guided contract reviewer.
-- Compensation: revoke discovery RPC access; all original source history remains.
BEGIN;
CREATE FUNCTION private.contract_reference_candidates(p_workspace uuid,p_contract uuid,p_version integer,p_purpose text,p_after uuid,p_limit integer)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE candidate record; items jsonb:='[]'::jsonb; next_after uuid; last_id uuid; seen integer:=0;
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Contract source discovery authority required' USING ERRCODE='42501'; END IF;
 IF p_purpose IS NULL OR p_purpose NOT IN ('purchase_contract','title_report','assignment_agreement','seller_disclosure','assignee_disclosure','closing_statement','supporting_document')
  OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 50 THEN RAISE EXCEPTION 'Bounded source purpose and page required' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM public.acquisition_contract_versions WHERE workspace_id=p_workspace AND deal_id=p_contract AND version=p_version;
 IF NOT FOUND THEN RAISE EXCEPTION 'Contract version unavailable' USING ERRCODE='42501'; END IF;
 -- One artifact row, even when several terms cite it. Withdrawn references remain
 -- discoverable for history and original-reviewer withdrawal, never approval.
 FOR candidate IN SELECT a.id,a.created_at FROM public.acquisition_evidence_artifacts a
  WHERE a.workspace_id=p_workspace AND a.contract_id=p_contract AND a.campaign_id IS NULL
   AND a.purpose=p_purpose AND a.contract_version<=p_version AND (p_after IS NULL OR a.id>p_after)
   AND EXISTS(SELECT 1 FROM private.contract_document_reference(p_workspace,p_contract,p_version,a.id))
  ORDER BY a.id LIMIT p_limit+1 LOOP
  seen:=seen+1;
  IF seen>p_limit THEN next_after:=last_id; EXIT; END IF;
  items:=items||jsonb_build_array(private.contract_reference_state(p_workspace,p_contract,p_version,candidate.id)
   ||jsonb_build_object('source_created_at',candidate.created_at));
  last_id:=candidate.id;
 END LOOP;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'purpose',p_purpose,
  'items',items,'next_after',next_after,'checked_at',statement_timestamp(),'execution_authorized',false);
END $$;
CREATE FUNCTION public.contract_reference_candidates(p_workspace uuid,p_contract uuid,p_version integer,p_purpose text,p_after uuid,p_limit integer)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.contract_reference_candidates(p_workspace,p_contract,p_version,p_purpose,p_after,p_limit)
$$;
REVOKE ALL ON FUNCTION private.contract_reference_candidates(uuid,uuid,integer,text,uuid,integer),public.contract_reference_candidates(uuid,uuid,integer,text,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.contract_reference_candidates(uuid,uuid,integer,text,uuid,integer),public.contract_reference_candidates(uuid,uuid,integer,text,uuid,integer) TO authenticated;
COMMIT;
