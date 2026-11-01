-- Private recursive title/disposition support. Original transition roots remain.
-- No public writer/choice/transition activation. Compensation: retain and forward-fix.
BEGIN;
CREATE FUNCTION private.title_review_effective_current(p_root uuid,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE original public.acquisition_contract_reviews%ROWTYPE; review public.acquisition_contract_reviews%ROWTYPE; policy private.acquisition_contract_review_policies%ROWTYPE;
 execution public.acquisition_contract_transitions%ROWTYPE; bound jsonb; fresh_until timestamptz;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN false; END IF;
 SELECT * INTO original FROM public.acquisition_contract_reviews WHERE id=p_root AND kind='title_findings' AND renewal_root_id IS NULL;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_lineage_head(
  original.workspace_id,original.contract_id,original.contract_version,p_root,p_at);
 IF NOT FOUND OR NOT private.acquisition_review_dependencies_match(review.id,p_at) THEN RETURN false; END IF;
 IF NOT FOUND OR review.status<>'approved' OR review.created_at>p_at OR review.expires_at<=p_at
  OR review.title_policy_snapshot IS NULL OR NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled)
  OR review.id IS DISTINCT FROM (SELECT id FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id
   AND contract_id=review.contract_id AND contract_version=review.contract_version AND kind='title_findings' ORDER BY sequence DESC LIMIT 1)
  THEN RETURN false; END IF;
 SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE workspace_id=review.workspace_id AND id=review.policy_id;
 IF NOT FOUND OR to_jsonb(policy) IS DISTINCT FROM review.title_policy_snapshot OR policy.revoked_at IS NOT NULL
  OR policy.kind<>'title_findings' OR policy.purpose<>'title_report' OR policy.reviewer_id<>review.actor_id
  OR policy.valid_from>review.created_at OR policy.valid_until<=p_at OR review.expires_at>policy.valid_until
  OR review.expires_at>review.created_at+make_interval(secs=>policy.max_review_seconds) THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.deals d JOIN public.workspaces w ON w.id=d.workspace_id
  JOIN public.workspace_memberships m ON m.workspace_id=w.id AND m.user_id=review.actor_id
  JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions s ON s.user_id=m.user_id AND s.id=review.session_id
  WHERE d.workspace_id=review.workspace_id AND d.id=review.contract_id AND d.acquisition_version=review.contract_version
   AND d.acquisition_status IN ('title_review','disposition_review') AND w.status='active' AND m.status='active' AND m.role IN ('owner','admin')
   AND m.updated_at=review.actor_membership_updated_at AND profile.status='approved'
   AND (s.not_after IS NULL OR (p_at<s.not_after AND review.expires_at<=s.not_after))) THEN RETURN false; END IF;
 SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE id=review.title_execution_transition_id
  AND workspace_id=review.workspace_id AND contract_id=review.contract_id AND contract_version=review.contract_version
  AND sequence=2 AND recorded_status='executed';
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions WHERE workspace_id=review.workspace_id
  AND contract_id=review.contract_id AND contract_version=review.contract_version AND sequence=3 AND recorded_status='title_review'
  AND execution_review_id=execution.execution_review_id)
  OR NOT private.execution_review_effective_current(execution.execution_review_id,p_at)
  OR review.expires_at>(SELECT expires_at FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_lineage_head(review.workspace_id,review.contract_id,review.contract_version,execution.execution_review_id,p_at)) THEN RETURN false; END IF;
 IF private.valid_title_findings(review.title_findings,review.contract_version,true) IS DISTINCT FROM true
  OR private.valid_title_source_journal(review.title_findings,review.title_sources,review.contract_version,review.artifact_id,
   review.source_version,review.verification_id,review.sha256) IS DISTINCT FROM true THEN RETURN false; END IF;
 fresh_until:=private.title_report_fresh_until(review.title_findings->'report_as_of',policy,p_at);
 IF fresh_until IS NULL OR review.expires_at>fresh_until THEN RETURN false; END IF;
 FOR bound IN SELECT value FROM jsonb_array_elements(review.title_sources) LOOP
  IF (bound->>'expires_at')::timestamptz<review.expires_at OR NOT EXISTS(SELECT 1 FROM private.contract_document_reference(
    review.workspace_id,review.contract_id,review.contract_version,(bound->>'artifact_id')::uuid) ref
    WHERE ref.source_version=(bound->>'source_version')::integer AND NOT ref.link_revoked)
   OR NOT private.contract_review_evidence_current(review.workspace_id,review.contract_id,(bound->>'source_version')::integer,
    (bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',p_at) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION private.title_review_effective_current(uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION private.disposition_review_effective_current(p_root uuid,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE original public.acquisition_contract_reviews%ROWTYPE; review public.acquisition_contract_reviews%ROWTYPE; title public.acquisition_contract_reviews%ROWTYPE;
 plan public.acquisition_disposition_plans%ROWTYPE; execution public.acquisition_contract_transitions%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; scope private.acquisition_disposition_policy_scopes%ROWTYPE;
 bound jsonb;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN false; END IF;
 SELECT * INTO original FROM public.acquisition_contract_reviews WHERE id=p_root AND kind='disposition_findings' AND renewal_root_id IS NULL;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_lineage_head(
  original.workspace_id,original.contract_id,original.contract_version,p_root,p_at);
 IF NOT FOUND OR NOT private.acquisition_review_dependencies_match(review.id,p_at) THEN RETURN false; END IF;
 IF NOT FOUND OR review.status<>'approved' OR review.created_at>p_at OR review.expires_at<=p_at
  OR review.disposition_policy_snapshot IS NULL OR review.id IS DISTINCT FROM (
   SELECT id FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id AND contract_id=review.contract_id
    AND contract_version=review.contract_version AND kind='disposition_findings' ORDER BY sequence DESC LIMIT 1)
  OR NOT private.disposition_policy_current(review.workspace_id,review.policy_id,review.actor_id,
   review.disposition_exit_type,p_at,review.disposition_policy_snapshot) THEN RETURN false; END IF;
 SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE id=review.policy_id;
 SELECT * INTO scope FROM private.acquisition_disposition_policy_scopes WHERE policy_id=review.policy_id;
 IF policy.valid_from>review.created_at OR scope.valid_from>review.created_at
  OR review.expires_at>least(policy.valid_until,scope.valid_until,review.created_at+make_interval(secs=>policy.max_review_seconds))
  OR NOT EXISTS(SELECT 1 FROM public.workspace_memberships m JOIN public.profiles profile ON profile.id=m.user_id
   JOIN public.workspaces w ON w.id=m.workspace_id JOIN auth.sessions sess ON sess.user_id=m.user_id AND sess.id=review.session_id
   WHERE m.workspace_id=review.workspace_id AND m.user_id=review.actor_id AND w.status='active' AND m.status='active'
    AND m.role IN ('owner','admin') AND m.updated_at=review.actor_membership_updated_at AND profile.status='approved'
    AND (sess.not_after IS NULL OR (p_at<sess.not_after AND review.expires_at<=sess.not_after))) THEN RETURN false; END IF;
 SELECT * INTO plan FROM public.acquisition_disposition_plans WHERE workspace_id=review.workspace_id AND contract_id=review.contract_id
  AND contract_version=review.contract_version ORDER BY sequence DESC LIMIT 1;
 IF NOT FOUND OR plan.id<>review.disposition_plan_id OR plan.status<>'proposed' OR plan.exit_type<>review.disposition_exit_type
  OR plan.execution_transition_id<>review.disposition_execution_id OR plan.title_entry_id<>review.disposition_title_entry_id THEN RETURN false; END IF;
 SELECT * INTO title FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id AND contract_id=review.contract_id
  AND contract_version=review.contract_version AND kind='title_findings'
  AND id=private.acquisition_review_lineage_head(review.workspace_id,review.contract_id,review.contract_version,review.disposition_title_review_id,p_at);
 IF NOT FOUND OR coalesce(title.renewal_root_id,title.id)<>review.disposition_title_review_id OR title.title_execution_transition_id<>plan.execution_transition_id
  OR NOT private.title_review_effective_current(review.disposition_title_review_id,p_at) OR review.expires_at>title.expires_at THEN RETURN false; END IF;
 SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE id=plan.execution_transition_id;
 IF NOT FOUND OR NOT private.execution_review_effective_current(execution.execution_review_id,p_at)
  OR review.expires_at>(SELECT expires_at FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_lineage_head(review.workspace_id,review.contract_id,review.contract_version,execution.execution_review_id,p_at)) THEN RETURN false; END IF;
 IF private.valid_disposition_findings(review.disposition_findings,review.contract_version,true,plan.exit_type) IS DISTINCT FROM true
  OR private.valid_disposition_source_journal(review.disposition_findings,review.disposition_sources,review.contract_version,
   review.artifact_id,review.source_version,review.verification_id,review.sha256) IS DISTINCT FROM true THEN RETURN false; END IF;
 IF plan.exit_type='wholesale_assignment' AND (NOT EXISTS(
   SELECT 1 FROM jsonb_array_elements(review.disposition_findings->'assignment'->'legal_basis'->'sources') c
    WHERE c->>'artifact_id'=scope.legal_source_id::text) OR NOT EXISTS(
   SELECT 1 FROM jsonb_array_elements(review.disposition_sources) c WHERE c->>'artifact_id'=scope.legal_source_id::text)) THEN RETURN false; END IF;
 FOR bound IN SELECT value FROM jsonb_array_elements(review.disposition_sources) LOOP
  IF (bound->>'expires_at')::timestamptz<review.expires_at OR NOT EXISTS(
   SELECT 1 FROM private.contract_document_reference(review.workspace_id,review.contract_id,review.contract_version,(bound->>'artifact_id')::uuid) ref
    WHERE ref.source_version=(bound->>'source_version')::integer AND NOT ref.link_revoked)
   OR NOT private.contract_review_evidence_current(review.workspace_id,review.contract_id,(bound->>'source_version')::integer,
    (bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',p_at) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION private.disposition_review_effective_current(uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;

COMMIT;
