-- Read-only title choices, including independent original withdrawal.
-- No policy provisioning, review creation or disposition/lifecycle authority.
-- Compensation: pause acquisition/revoke policies; retain all historical records.
BEGIN;
CREATE FUNCTION private.title_review_candidate(p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE checked timestamptz:=statement_timestamp(); state jsonb; status_name text; source_ref record;
 artifact public.acquisition_evidence_artifacts%ROWTYPE; scan public.acquisition_evidence_verifications%ROWTYPE;
 policy private.acquisition_contract_review_policies%ROWTYPE; prior public.acquisition_contract_reviews%ROWTYPE;
 execution public.acquisition_contract_transitions%ROWTYPE; executed public.acquisition_contract_reviews%ROWTYPE;
 deadline timestamptz; approval_deadline timestamptz; calendar_supported boolean:=false;
 candidate jsonb:=NULL; resolution jsonb:=NULL; withdrawal jsonb:=NULL;
BEGIN
 state:=private.title_review_state(p_workspace,p_contract,p_version);
 SELECT * INTO prior FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='title_findings' ORDER BY sequence DESC LIMIT 1;
 IF prior.status IN ('approved','requires_resolution') AND prior.actor_id=auth.uid() AND prior.sequence<2147483647 THEN
  withdrawal:=jsonb_build_object('review_id',prior.id,'artifact_id',prior.artifact_id,'source_version',prior.source_version,
   'verification_id',prior.verification_id,'policy_id',prior.policy_id,'expected_sequence',prior.sequence,'original_status',prior.status);
 END IF;
 -- A null selection can still recover/withdraw the latest original decision.
 IF p_artifact IS NOT NULL THEN
  SELECT * INTO source_ref FROM private.contract_document_reference(p_workspace,p_contract,p_version,p_artifact);
  IF NOT FOUND THEN RAISE EXCEPTION 'Title report reference unavailable' USING ERRCODE='42501'; END IF;
  SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=source_ref.source_version AND id=p_artifact AND purpose='title_report' AND campaign_id IS NULL;
  IF NOT FOUND THEN RAISE EXCEPTION 'Original title report unavailable' USING ERRCODE='42501'; END IF;
  SELECT * INTO scan FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=p_artifact ORDER BY created_at DESC,id DESC LIMIT 1;
 END IF;
 SELECT * INTO policy FROM private.acquisition_contract_review_policies WHERE workspace_id=p_workspace AND kind='title_findings'
  AND purpose='title_report' AND reviewer_id=auth.uid() AND revoked_at IS NULL AND valid_from<=checked AND checked<valid_until
  ORDER BY valid_from DESC,id DESC LIMIT 1;
 SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND sequence=2 AND recorded_status='executed';
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled) THEN status_name:='paused';
 ELSIF NOT EXISTS(SELECT 1 FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract AND acquisition_version=p_version AND acquisition_status='title_review')
  OR execution.id IS NULL OR NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
   AND contract_version=p_version AND sequence=3 AND recorded_status='title_review' AND execution_review_id=execution.execution_review_id) THEN status_name:='contract_unavailable';
 ELSIF coalesce(prior.sequence,0)>=2147483647 THEN status_name:='history_limit_reached';
 ELSIF p_artifact IS NULL THEN status_name:='document_required';
 ELSIF policy.id IS NULL THEN status_name:='reviewer_policy_required';
 ELSIF source_ref.link_revoked OR scan.id IS NULL OR NOT private.contract_review_evidence_current(p_workspace,p_contract,source_ref.source_version,p_artifact,scan.id,artifact.expected_sha256,'title_report',checked) THEN status_name:='evidence_review_required';
 ELSE
  SELECT least(artifact.retain_until,rp.valid_until,k.valid_until,ks.valid_until,scanner_session.not_after,
   reviewer_session.not_after,policy.valid_until,checked+make_interval(secs=>policy.max_review_seconds)) INTO deadline
  FROM private.acquisition_evidence_verification_keys k
  JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose='title_report'
  JOIN private.acquisition_evidence_policies rp ON rp.workspace_id=k.workspace_id AND rp.id=artifact.retention_policy_id
  JOIN auth.sessions scanner_session ON scanner_session.id=scan.session_id AND scanner_session.user_id=scan.actor_id
  JOIN auth.sessions reviewer_session ON reviewer_session.id=(auth.jwt()->>'session_id')::uuid AND reviewer_session.user_id=auth.uid()
  WHERE k.workspace_id=p_workspace AND k.id=scan.key_id;
  IF deadline IS NULL OR deadline<=checked THEN status_name:='evidence_review_required';
  ELSE
   resolution:=jsonb_build_object('artifact_id',p_artifact,'source_version',source_ref.source_version,'verification_id',scan.id,
    'sha256',artifact.expected_sha256,'policy_id',policy.id,'available_until',deadline,'expected_sequence',(state->>'sequence')::integer);
   SELECT * INTO executed FROM public.acquisition_contract_reviews WHERE id=execution.execution_review_id;
   calendar_supported:=policy.title_report_max_age_days IS NOT NULL AND EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=policy.title_report_timezone);
   IF NOT private.execution_review_current(executed.id,checked) THEN status_name:='execution_review_required';
   ELSIF policy.title_report_max_age_seconds IS NULL AND NOT calendar_supported THEN status_name:='report_freshness_policy_required';
   ELSE
    approval_deadline:=least(deadline,executed.expires_at);
    IF approval_deadline<=checked THEN status_name:='execution_review_required';
    ELSE
     status_name:='ready_for_human_review';
     candidate:=resolution||jsonb_build_object('max_expires_at',approval_deadline,'report_policy',jsonb_build_object(
      'max_age_seconds',policy.title_report_max_age_seconds,
      'max_age_days',CASE WHEN calendar_supported THEN policy.title_report_max_age_days END,
      'timezone',CASE WHEN calendar_supported THEN policy.title_report_timezone END));
    END IF;
   END IF;
  END IF;
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'artifact_id',p_artifact,
  'status',status_name,'candidate',candidate,'resolution',resolution,'withdrawal',withdrawal,
  'current_review',state,'checked_at',checked,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.title_review_candidate(uuid,uuid,integer,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.title_review_candidate(uuid,uuid,integer,uuid) TO authenticated;
CREATE FUNCTION public.title_review_candidate(p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.title_review_candidate(p_workspace,p_contract,p_version,p_artifact)
$$;
REVOKE ALL ON FUNCTION public.title_review_candidate(uuid,uuid,integer,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.title_review_candidate(uuid,uuid,integer,uuid) TO authenticated;
COMMIT;
