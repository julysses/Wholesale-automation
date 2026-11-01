-- Current deadline interpretation authority is distinct from a historical save receipt.
-- No policy provisioning, lifecycle change or execution authority.
-- Compensation: pause acquisition/revoke policy; retain review/source/audit history.
BEGIN;
CREATE FUNCTION private.deadline_review_current(p_review uuid,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE review public.acquisition_contract_reviews%ROWTYPE; prepared jsonb; bound jsonb; original_source public.acquisition_contract_term_sources%ROWTYPE;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN false; END IF;
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=p_review AND kind='deadline_resolution';
 IF NOT FOUND OR review.status<>'approved' OR review.created_at>p_at OR review.expires_at<=p_at
  OR NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled)
  OR review.id IS DISTINCT FROM (SELECT id FROM public.acquisition_contract_reviews WHERE workspace_id=review.workspace_id
   AND contract_id=review.contract_id AND contract_version=review.contract_version AND kind='deadline_resolution'
   AND deadline_term=review.deadline_term ORDER BY sequence DESC LIMIT 1)
  THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_contract_review_policies policy
  JOIN public.workspace_memberships m ON m.workspace_id=policy.workspace_id AND m.user_id=review.actor_id
  JOIN public.profiles profile ON profile.id=m.user_id JOIN auth.sessions s ON s.id=review.session_id AND s.user_id=m.user_id
  JOIN public.deals d ON d.workspace_id=policy.workspace_id AND d.id=review.contract_id
  JOIN public.workspaces w ON w.id=d.workspace_id AND w.status='active'
  WHERE policy.id=review.policy_id AND policy.workspace_id=review.workspace_id AND policy.kind='deadline_resolution'
   AND policy.purpose=review.purpose AND policy.reviewer_id=review.actor_id AND policy.revoked_at IS NULL
   AND policy.valid_from<=review.created_at AND p_at<policy.valid_until AND review.expires_at<=policy.valid_until
   AND review.expires_at<=review.created_at+make_interval(secs=>policy.max_review_seconds)
   AND m.status='active' AND m.role IN ('owner','admin') AND m.updated_at=review.actor_membership_updated_at
   AND profile.status='approved' AND (s.not_after IS NULL OR (p_at<s.not_after AND review.expires_at<=s.not_after))
   AND d.acquisition_version=review.contract_version AND d.acquisition_status IN ('pending_signature','executed')) THEN RETURN false; END IF;
 SELECT terms INTO prepared FROM public.acquisition_contract_versions
  WHERE workspace_id=review.workspace_id AND deal_id=review.contract_id AND version=review.contract_version;
 IF NOT private.valid_deadline_resolution(review.deadline_resolution,review.contract_version)
  OR prepared->review.deadline_term->>'precision' IS DISTINCT FROM 'date'
  OR prepared->review.deadline_term->>'calendar_date' IS DISTINCT FROM review.deadline_resolution->>'calendar_date'
  OR jsonb_typeof(review.deadline_sources) IS DISTINCT FROM 'array'
  OR jsonb_array_length(review.deadline_sources) NOT BETWEEN 1 AND 2 THEN RETURN false; END IF;
 -- The retained interpretation agreement must be in the server-derived source journal.
 IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(review.deadline_sources) item WHERE
  item->>'artifact_id'=review.artifact_id::text AND item->>'source_version'=review.source_version::text
  AND item->>'verification_id'=review.verification_id::text AND item->>'sha256'=review.sha256 AND item->>'purpose'=review.purpose) THEN RETURN false; END IF;
 SELECT * INTO original_source FROM public.acquisition_contract_term_sources
  WHERE workspace_id=review.workspace_id AND contract_id=review.contract_id AND contract_version=review.contract_version AND term=review.deadline_term;
 IF NOT FOUND OR NOT EXISTS(SELECT 1 FROM jsonb_array_elements(review.deadline_sources) item WHERE
  item->>'artifact_id'=original_source.artifact_id::text AND item->>'source_version'=original_source.artifact_version::text
  AND item->>'verification_id'=original_source.verification_id::text AND item->>'sha256'=original_source.sha256) THEN RETURN false; END IF;
 FOR bound IN SELECT value FROM jsonb_array_elements(review.deadline_sources) LOOP
  IF NOT(bound ?& ARRAY['artifact_id','source_version','verification_id','sha256','purpose','expires_at'])
   OR (bound->>'expires_at')::timestamptz IS NULL OR (bound->>'expires_at')::timestamptz<review.expires_at
   OR (bound->>'source_version')::integer NOT BETWEEN 1 AND review.contract_version
   OR NOT EXISTS(SELECT 1 FROM private.contract_document_reference(review.workspace_id,review.contract_id,review.contract_version,(bound->>'artifact_id')::uuid) ref
    WHERE ref.source_version=(bound->>'source_version')::integer AND NOT ref.link_revoked)
   OR NOT private.contract_review_evidence_current(review.workspace_id,review.contract_id,(bound->>'source_version')::integer,
    (bound->>'artifact_id')::uuid,(bound->>'verification_id')::uuid,bound->>'sha256',bound->>'purpose',p_at) THEN RETURN false; END IF;
 END LOOP;
 RETURN true;
EXCEPTION WHEN invalid_text_representation OR invalid_datetime_format OR numeric_value_out_of_range OR datetime_field_overflow THEN RETURN false;
END $$;
REVOKE ALL ON FUNCTION private.deadline_review_current(uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.deadline_review_state(p_workspace uuid,p_contract uuid,p_version integer,p_term text) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE latest public.acquisition_contract_reviews%ROWTYPE; current_review boolean:=false;
 checked timestamptz:=statement_timestamp(); status_name text; seq integer; original_term jsonb; resolution jsonb;
BEGIN
 IF p_term IS NULL OR p_term NOT IN ('effective','inspection_deadline','closing_deadline') THEN
  RAISE EXCEPTION 'Exact deadline term required' USING ERRCODE='22023'; END IF;
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') OR NOT EXISTS(
   SELECT 1 FROM public.acquisition_contract_versions WHERE workspace_id=p_workspace AND deal_id=p_contract AND version=p_version) THEN
  RAISE EXCEPTION 'Deadline review access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO latest FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='deadline_resolution' AND deadline_term=p_term ORDER BY sequence DESC LIMIT 1;
 SELECT coalesce(max(sequence),0) INTO seq FROM public.acquisition_contract_reviews
  WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND kind='deadline_resolution';
 SELECT coalesce(terms->p_term,'{"precision":"unknown"}'::jsonb) INTO original_term FROM public.acquisition_contract_versions
  WHERE workspace_id=p_workspace AND deal_id=p_contract AND version=p_version;
 IF latest.id IS NOT NULL THEN
  SELECT deadline_resolution INTO resolution FROM public.acquisition_contract_reviews WHERE id=coalesce(latest.deadline_original_review_id,latest.id);
 END IF;
 IF latest.id IS NOT NULL THEN current_review:=private.deadline_review_current(latest.id,checked); END IF;
 status_name:=CASE WHEN latest.id IS NULL THEN 'not_reviewed' WHEN latest.status='withdrawn' THEN 'withdrawn'
  WHEN current_review THEN 'approved' ELSE 'requires_review' END;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'kind','deadline_resolution',
  'term',p_term,'sequence',seq,'review_sequence',latest.sequence,'review_id',latest.id,
  'interpretation_review_id',coalesce(latest.deadline_original_review_id,latest.id),'original_term',original_term,'resolution',resolution,'status',status_name,'approval_current',current_review,
  'expires_at',CASE WHEN current_review THEN latest.expires_at ELSE NULL END,'checked_at',checked,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.deadline_review_state(uuid,uuid,integer,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.deadline_review_state(uuid,uuid,integer,text) TO authenticated;
CREATE FUNCTION public.deadline_review_state(p_workspace uuid,p_contract uuid,p_version integer,p_term text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.deadline_review_state(p_workspace,p_contract,p_version,p_term)
$$;
REVOKE ALL ON FUNCTION public.deadline_review_state(uuid,uuid,integer,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.deadline_review_state(uuid,uuid,integer,text) TO authenticated;
COMMIT;
