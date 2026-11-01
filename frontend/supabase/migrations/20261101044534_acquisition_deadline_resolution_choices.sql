-- Read-only choices for one preserved calendar date and interpretation source. Writes independently recheck
-- every source, input and policy. No policies, reviews or lifecycle changes created.
-- Compensation: pause acquisition/revoke policy; retain review and source history.
BEGIN;
CREATE FUNCTION private.deadline_review_candidate(p_workspace uuid,p_contract uuid,p_version integer,p_term text,p_artifact uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE checked timestamptz:=statement_timestamp(); state jsonb; status_name text; source_ref record; prepared jsonb;
 artifact public.acquisition_evidence_artifacts%ROWTYPE; scan public.acquisition_evidence_verifications%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; prior public.acquisition_contract_reviews%ROWTYPE;
 original_source public.acquisition_contract_term_sources%ROWTYPE; original_deadline timestamptz; source_choice jsonb:=NULL;
 deadline timestamptz; candidate jsonb:=NULL; withdrawal jsonb:=NULL;
BEGIN
 state:=private.deadline_review_state(p_workspace,p_contract,p_version,p_term);
 SELECT terms INTO prepared FROM public.acquisition_contract_versions WHERE workspace_id=p_workspace AND deal_id=p_contract AND version=p_version;
 SELECT * INTO source_ref FROM private.contract_document_reference(p_workspace,p_contract,p_version,p_artifact);
 IF NOT FOUND THEN RAISE EXCEPTION 'Interpretation source reference unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=source_ref.source_version AND id=p_artifact AND purpose='purchase_contract' AND campaign_id IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'Interpretation source unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO prior FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='deadline_resolution' AND deadline_term=p_term ORDER BY sequence DESC LIMIT 1;
 -- Withdrawal remains bound to the original review even if another file is selected.
 IF prior.status='approved' AND prior.actor_id=auth.uid() AND (state->>'sequence')::integer<2147483647 THEN
  withdrawal:=jsonb_build_object('review_id',prior.id,'artifact_id',prior.artifact_id,'source_version',prior.source_version,
   'verification_id',prior.verification_id,'policy_id',prior.policy_id,'expected_sequence',(state->>'sequence')::integer);
 END IF;
 SELECT * INTO original_source FROM public.acquisition_contract_term_sources
  WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND term=p_term;
 IF FOUND THEN
  source_choice:=jsonb_build_object('term',p_term,'artifact_id',original_source.artifact_id,
   'artifact_version',original_source.artifact_version,'verification_id',original_source.verification_id,
   'sha256',original_source.sha256,'locator',original_source.locator);
  SELECT least(a.retain_until,rp.valid_until,k.valid_until,ks.valid_until,scanner_session.not_after) INTO original_deadline
  FROM public.acquisition_evidence_artifacts a
  JOIN public.acquisition_evidence_verifications v ON v.workspace_id=a.workspace_id AND v.artifact_id=a.id AND v.id=original_source.verification_id
  JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=a.workspace_id AND rp.id=a.retention_policy_id
  JOIN private.acquisition_evidence_verification_keys k ON k.workspace_id=v.workspace_id AND k.id=v.key_id
  JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=a.purpose
  JOIN auth.sessions scanner_session ON scanner_session.id=v.session_id AND scanner_session.user_id=v.actor_id
  WHERE a.workspace_id=p_workspace AND a.contract_id=p_contract AND a.contract_version=original_source.artifact_version
   AND a.id=original_source.artifact_id AND a.expected_sha256=original_source.sha256
   AND EXISTS(SELECT 1 FROM private.contract_document_reference(p_workspace,p_contract,p_version,a.id) r
     WHERE r.source_version=original_source.artifact_version AND NOT r.link_revoked)
   AND private.contract_review_evidence_current(p_workspace,p_contract,original_source.artifact_version,a.id,v.id,original_source.sha256,a.purpose,checked);
 END IF;
 SELECT * INTO scan FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=p_artifact ORDER BY created_at DESC,id DESC LIMIT 1;
 SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE workspace_id=p_workspace AND kind='deadline_resolution'
  AND purpose='purchase_contract' AND reviewer_id=auth.uid() AND revoked_at IS NULL AND valid_from<=checked AND checked<valid_until
  ORDER BY valid_from DESC,id DESC LIMIT 1;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled) THEN status_name:='paused';
 ELSIF NOT EXISTS(SELECT 1 FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract AND acquisition_version=p_version AND acquisition_status='pending_signature') THEN status_name:='contract_unavailable';
 ELSIF (state->>'sequence')::integer>=2147483647 THEN status_name:='history_limit_reached';
 ELSIF prepared IS NULL OR NOT private.valid_contract_terms(prepared) THEN status_name:='prepared_terms_required';
 ELSIF prepared->p_term->>'precision' IS DISTINCT FROM 'date' THEN status_name:='original_date_required';
 ELSIF original_deadline IS NULL OR original_deadline<=checked THEN status_name:='original_evidence_review_required';
 ELSIF policy.id IS NULL THEN status_name:='reviewer_policy_required';
 ELSIF source_ref.link_revoked OR scan.id IS NULL OR NOT private.contract_review_evidence_current(p_workspace,p_contract,source_ref.source_version,p_artifact,scan.id,artifact.expected_sha256,'purchase_contract',checked) THEN status_name:='evidence_review_required';
 ELSE
  SELECT least(original_deadline,artifact.retain_until,rp.valid_until,k.valid_until,ks.valid_until,scanner_session.not_after,
   reviewer_session.not_after,policy.valid_until,checked+make_interval(secs=>policy.max_review_seconds)) INTO deadline
  FROM private.acquisition_evidence_verification_keys k
  JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose='purchase_contract'
  JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=k.workspace_id AND rp.id=artifact.retention_policy_id
  JOIN auth.sessions scanner_session ON scanner_session.id=scan.session_id AND scanner_session.user_id=scan.actor_id
  JOIN auth.sessions reviewer_session ON reviewer_session.id=(auth.jwt()->>'session_id')::uuid AND reviewer_session.user_id=auth.uid()
  WHERE k.workspace_id=p_workspace AND k.id=scan.key_id;
  IF deadline IS NULL OR deadline<=checked THEN status_name:='evidence_review_required';
  ELSE
   status_name:='ready_for_human_review';
   candidate:=jsonb_build_object('artifact_id',p_artifact,'source_version',source_ref.source_version,'verification_id',scan.id,
    'sha256',artifact.expected_sha256,'policy_id',policy.id,'max_expires_at',deadline,'expected_sequence',(state->>'sequence')::integer);
  END IF;
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'artifact_id',p_artifact,
  'term',p_term,'status',status_name,'candidate',candidate,'withdrawal',withdrawal,'original_source',source_choice,
  'current_review',state,'checked_at',checked,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.deadline_review_candidate(uuid,uuid,integer,text,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.deadline_review_candidate(uuid,uuid,integer,text,uuid) TO authenticated;
CREATE FUNCTION public.deadline_review_candidate(p_workspace uuid,p_contract uuid,p_version integer,p_term text,p_artifact uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.deadline_review_candidate(p_workspace,p_contract,p_version,p_term,p_artifact)
$$;
REVOKE ALL ON FUNCTION public.deadline_review_candidate(uuid,uuid,integer,text,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.deadline_review_candidate(uuid,uuid,integer,text,uuid) TO authenticated;
COMMIT;
