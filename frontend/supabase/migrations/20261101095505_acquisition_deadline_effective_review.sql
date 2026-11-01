-- Private root-aware deadline authority; no existing public workflow is switched.
-- Original expiry, interpretation and term-source history remain immutable.
-- Compensation: retain history and leave renewal execution unavailable.
BEGIN;
CREATE FUNCTION private.deadline_review_effective_current(p_root uuid,p_at timestamptz) RETURNS boolean
LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE original public.acquisition_contract_reviews%ROWTYPE; review public.acquisition_contract_reviews%ROWTYPE; prepared jsonb; bound jsonb; original_source public.acquisition_contract_term_sources%ROWTYPE;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) THEN RETURN false; END IF;
 SELECT * INTO original FROM public.acquisition_contract_reviews WHERE id=p_root AND kind='deadline_resolution' AND renewal_root_id IS NULL;
 IF NOT FOUND THEN RETURN false; END IF;
 SELECT * INTO review FROM public.acquisition_contract_reviews WHERE id=private.acquisition_review_lineage_head(
  original.workspace_id,original.contract_id,original.contract_version,p_root,p_at);
 IF NOT FOUND OR NOT private.acquisition_review_dependencies_match(review.id,p_at) THEN RETURN false; END IF;
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
   AND d.acquisition_version=review.contract_version AND d.acquisition_status IN ('pending_signature','executed','title_review','disposition_review')) THEN RETURN false; END IF;
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
  AND (review.renewal_root_id IS NOT NULL OR item->>'verification_id'=original_source.verification_id::text)
  AND item->>'sha256'=original_source.sha256) THEN RETURN false; END IF;
 -- Renewals may bind a fresh scan of the exact original bytes. Each referenced
 -- scan must still be current under the full scanner/retention/reference checks.
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
REVOKE ALL ON FUNCTION private.deadline_review_effective_current(uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
COMMIT;
