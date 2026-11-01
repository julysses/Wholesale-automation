-- Current execution evidence is distinct from a historical save receipt.
-- No policy provisioning, lifecycle change or execution authority.
-- Compensation: pause acquisition/revoke policy; retain review/source/audit history.
BEGIN;
CREATE FUNCTION private.execution_review_current(p_review uuid,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE review public.acquisition_contract_reviews%ROWTYPE; prepared jsonb; bound jsonb; source jsonb;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN false; END IF;
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=p_review AND kind='executed_contract';
 IF NOT FOUND OR review.status<>'approved' OR review.created_at>p_at OR review.expires_at<=p_at
  OR NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled)
  OR review.id IS DISTINCT FROM (SELECT id FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id
   AND contract_id=review.contract_id AND contract_version=review.contract_version AND kind='executed_contract' ORDER BY sequence DESC LIMIT 1)
  THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_contract_review_policies policy
  JOIN public.workspace_memberships m ON m.workspace_id=policy.workspace_id AND m.user_id=review.actor_id
  JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions s ON s.id=review.session_id AND s.user_id=m.user_id
  JOIN public.deals d ON d.workspace_id=policy.workspace_id AND d.id=review.contract_id
  WHERE policy.id=review.policy_id AND policy.workspace_id=review.workspace_id AND policy.kind='executed_contract'
   AND policy.purpose=review.purpose AND policy.reviewer_id=review.actor_id AND policy.revoked_at IS NULL
   AND policy.valid_from<=review.created_at AND p_at<policy.valid_until AND review.expires_at<=policy.valid_until
   AND review.expires_at<=review.created_at+make_interval(secs=>policy.max_review_seconds)
   AND m.status='active' AND m.role IN ('owner','admin') AND m.updated_at=review.actor_membership_updated_at
   AND profile.status='approved' AND (s.not_after IS NULL OR (p_at<s.not_after AND review.expires_at<=s.not_after))
   AND d.acquisition_version=review.contract_version AND d.acquisition_status NOT IN ('draft','closed','cancelled','expired')) THEN RETURN false; END IF;
 SELECT terms INTO prepared FROM public.acquisition_contract_versions
  WHERE workspace_id=review.workspace_id AND deal_id=review.contract_id AND version=review.contract_version;
 IF NOT private.valid_execution_findings(review.execution_findings,review.contract_version)
  OR NOT private.execution_terms_match(review.execution_findings->'terms',prepared,p_at)
  OR jsonb_typeof(review.execution_sources) IS DISTINCT FROM 'array'
  OR jsonb_array_length(review.execution_sources) NOT BETWEEN 1 AND 7 THEN RETURN false; END IF;
 -- The retained main agreement must be in the server-derived source journal.
 IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(review.execution_sources) item WHERE
  item->>'artifact_id'=review.artifact_id::text AND item->>'source_version'=review.source_version::text
  AND item->>'verification_id'=review.verification_id::text AND item->>'sha256'=review.sha256 AND item->>'purpose'=review.purpose) THEN RETURN false; END IF;
 FOR source IN SELECT value FROM jsonb_array_elements(review.execution_findings->'terms'->'sources') LOOP
  IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(review.execution_sources) item WHERE
   item->>'artifact_id'=source->>'artifact_id' AND item->>'source_version'=source->>'artifact_version'
   AND item->>'sha256'=source->>'sha256') THEN RETURN false; END IF;
 END LOOP;
 FOR bound IN SELECT value FROM jsonb_array_elements(review.execution_sources) LOOP
  IF NOT(bound ?& ARRAY['artifact_id','source_version','verification_id','sha256','purpose','expires_at'])
   OR (bound->>'expires_at')::timestamptz IS NULL OR (bound->>'expires_at')::timestamptz<review.expires_at
   OR (bound->>'source_version')::integer NOT BETWEEN 1 AND review.contract_version
   OR NOT EXISTS(SELECT 1 FROM private.contract_document_reference(review.workspace_id,review.contract_id,review.contract_version,(bound->>'artifact_id')::uuid) ref
    WHERE ref.source_version=(bound->>'source_version')::integer AND NOT ref.link_revoked)
   OR NOT private.contract_review_evidence_current(review.workspace_id,review.contract_id,(bound->>'source_version')::integer,
    (bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',p_at) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION private.execution_review_current(uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.execution_review_state(p_workspace uuid,p_contract uuid,p_version integer) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE latest public.acquisition_contract_reviews%ROWTYPE; current_review boolean:=false;
 checked timestamptz:=statement_timestamp(); status_name text;
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') OR NOT EXISTS(
   SELECT 1 FROM public.acquisition_contract_versions WHERE workspace_id=p_workspace AND deal_id=p_contract AND version=p_version) THEN
  RAISE EXCEPTION 'Execution review access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO latest FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='executed_contract' ORDER BY sequence DESC LIMIT 1;
 IF latest.id IS NOT NULL THEN current_review:=private.execution_review_current(latest.id,checked); END IF;
 status_name:=CASE WHEN latest.id IS NULL THEN 'not_reviewed' WHEN latest.status='withdrawn' THEN 'withdrawn'
  WHEN current_review THEN 'approved' ELSE 'requires_review' END;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'kind','executed_contract',
  'sequence',coalesce(latest.sequence,0),'review_id',latest.id,'status',status_name,'approval_current',current_review,
  'expires_at',CASE WHEN current_review THEN latest.expires_at ELSE NULL END,'checked_at',checked,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.execution_review_state(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.execution_review_state(uuid,uuid,integer) TO authenticated;
CREATE FUNCTION public.execution_review_state(p_workspace uuid,p_contract uuid,p_version integer) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.execution_review_state(p_workspace,p_contract,p_version)
$$;
REVOKE ALL ON FUNCTION public.execution_review_state(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.execution_review_state(uuid,uuid,integer) TO authenticated;
COMMIT;
