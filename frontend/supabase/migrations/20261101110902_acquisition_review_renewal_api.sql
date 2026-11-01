-- Bounded owner/admin renewal discovery and exact personal-save RPC transport.
-- No lifecycle transitions, provider activation or transaction execution.
BEGIN;
CREATE FUNCTION private.acquisition_review_renewal_index(p_workspace uuid,p_contract uuid,p_version integer)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE original record; choice jsonb; items jsonb:='[]'; checked timestamptz:=statement_timestamp();
BEGIN
 PERFORM private.signature_review_state(p_workspace,p_contract,p_version);
 FOR original IN SELECT * FROM (
  SELECT DISTINCT ON (kind,coalesce(deadline_term,'')) id,kind,deadline_term FROM public.acquisition_contract_reviews
   WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND status='approved' AND renewal_root_id IS NULL
    AND kind IN ('deadline_resolution','executed_contract','title_findings','disposition_findings')
   ORDER BY kind,coalesce(deadline_term,''),sequence DESC) roots
  ORDER BY CASE kind WHEN 'deadline_resolution' THEN 1 WHEN 'executed_contract' THEN 2 WHEN 'title_findings' THEN 3 ELSE 4 END,
   CASE deadline_term WHEN 'effective' THEN 1 WHEN 'inspection_deadline' THEN 2 ELSE 3 END LIMIT 7 LOOP
  IF jsonb_array_length(items)>=6 THEN RAISE EXCEPTION 'Bounded original review set required' USING ERRCODE='55000'; END IF;
  choice:=private.acquisition_review_renewal_candidate(p_workspace,p_contract,p_version,original.id);
  items:=items||jsonb_build_array(jsonb_build_object('root_review_id',original.id,'kind',original.kind,'deadline_term',original.deadline_term,
   'status',choice->>'status','current_review',choice->'current_review'));
 END LOOP;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,
  'items',items,'checked_at',checked,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.acquisition_review_renewal_index(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_review_renewal_index(uuid,uuid,integer),
 private.acquisition_review_renewal_candidate(uuid,uuid,integer,uuid),
 private.record_acquisition_review_renewal(uuid,uuid,uuid,integer,text,text,integer,uuid,uuid,uuid,text,timestamptz,boolean,text) TO authenticated;
CREATE FUNCTION public.acquisition_review_renewal_index(p_workspace uuid,p_contract uuid,p_version integer)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.acquisition_review_renewal_index(p_workspace,p_contract,p_version)
$$;
CREATE FUNCTION public.acquisition_review_renewal_candidate(p_workspace uuid,p_contract uuid,p_version integer,p_root uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.acquisition_review_renewal_candidate(p_workspace,p_contract,p_version,p_root)
$$;
CREATE FUNCTION public.record_acquisition_review_renewal(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_kind text,p_term text,
 p_expected_sequence integer,p_root uuid,p_previous uuid,p_policy uuid,p_snapshot text,p_expires timestamptz,p_personally_reviewed boolean,p_note text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.record_acquisition_review_renewal(p_id,p_workspace,p_contract,p_version,p_kind,p_term,p_expected_sequence,p_root,p_previous,
  p_policy,p_snapshot,p_expires,p_personally_reviewed,p_note)
$$;
REVOKE ALL ON FUNCTION public.acquisition_review_renewal_index(uuid,uuid,integer),
 public.acquisition_review_renewal_candidate(uuid,uuid,integer,uuid),
 public.record_acquisition_review_renewal(uuid,uuid,uuid,integer,text,text,integer,uuid,uuid,uuid,text,timestamptz,boolean,text)
 FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.acquisition_review_renewal_index(uuid,uuid,integer),
 public.acquisition_review_renewal_candidate(uuid,uuid,integer,uuid),
 public.record_acquisition_review_renewal(uuid,uuid,uuid,integer,text,text,integer,uuid,uuid,uuid,text,timestamptz,boolean,text) TO authenticated;
-- Compensation: revoke these RPC/private execute grants or pause acquisition;
-- preserve all original/renewed reviews and audit history for a forward correction.
COMMIT;
