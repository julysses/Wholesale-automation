-- Read-only operator choices. No policy creation, review save or signing action.
-- Compensation: revoke RPC access; preserve all original evidence and decisions.
BEGIN;
CREATE FUNCTION private.signature_review_candidate(p_workspace uuid,p_contract uuid,p_version integer)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' AS $$
DECLARE state jsonb; checked timestamptz; status_name text; deadline timestamptz;
 basis public.acquisition_contract_reviews%ROWTYPE; prior public.acquisition_signature_reviews%ROWTYPE;
 policy private.acquisition_signature_policies%ROWTYPE; candidate jsonb:=NULL; withdrawal jsonb:=NULL;
BEGIN
 -- Reuse current owner/admin MFA, session, membership and retained-version access.
 state:=private.signature_review_state(p_workspace,p_contract,p_version);
 SELECT * INTO basis FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='contract_review' ORDER BY sequence DESC LIMIT 1;
 SELECT * INTO policy FROM private.acquisition_signature_policies WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND reviewer_id=auth.uid() AND basis_policy_id=basis.policy_id
  AND artifact_id=basis.artifact_id AND source_version=basis.source_version AND sha256=basis.sha256
  AND revoked_at IS NULL AND valid_from<=clock_timestamp() AND clock_timestamp()<valid_until
  ORDER BY valid_from DESC,id DESC LIMIT 1;
 -- Refresh state after lookup; withdrawals always bind the actual latest decision.
 state:=private.signature_review_state(p_workspace,p_contract,p_version);
 checked:=(state->>'checked_at')::timestamptz;
 SELECT * INTO prior FROM public.acquisition_signature_reviews WHERE id=(state->>'review_id')::uuid
  AND workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version;
 IF prior.status='approved' AND prior.actor_id=auth.uid() AND prior.sequence<2147483647 THEN
  withdrawal:=jsonb_build_object('review_id',prior.id,'basis_review_id',prior.basis_review_id,
   'policy_id',prior.policy_id,'expected_sequence',prior.sequence);
 END IF;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled) THEN status_name:='paused';
 ELSIF NOT EXISTS(SELECT 1 FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract AND acquisition_version=p_version AND acquisition_status='draft') THEN status_name:='contract_unavailable';
 ELSIF (state->>'sequence')::integer>=2147483647 THEN status_name:='history_limit_reached';
 ELSIF basis.id IS NULL OR NOT private.signature_basis_current(p_workspace,p_contract,p_version,basis.id,checked) THEN status_name:='contract_review_required';
 ELSIF policy.id IS NULL OR policy.revoked_at IS NOT NULL OR NOT(policy.valid_from<=checked AND checked<policy.valid_until) THEN status_name:='reviewer_policy_required';
 ELSE
  SELECT least(checked+make_interval(secs=>policy.max_review_seconds),policy.valid_until,basis.expires_at,
   release_session.not_after,review_session.not_after,basis_policy.valid_until,a.retain_until,retention.valid_until,
   k.valid_until,ks.valid_until,scan_session.not_after) INTO deadline
   FROM public.acquisition_evidence_artifacts a
   JOIN public.acquisition_evidence_verifications scan ON scan.workspace_id=a.workspace_id AND scan.artifact_id=a.id AND scan.id=basis.verification_id
   JOIN private.acquisition_evidence_policies retention ON retention.workspace_id=a.workspace_id AND retention.id=a.retention_policy_id
   JOIN private.acquisition_evidence_verification_keys k ON k.workspace_id=scan.workspace_id AND k.id=scan.key_id
   JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=a.purpose
   JOIN private.acquisition_contract_review_policies basis_policy ON basis_policy.workspace_id=a.workspace_id AND basis_policy.id=basis.policy_id
   JOIN auth.sessions scan_session ON scan_session.id=scan.session_id AND scan_session.user_id=scan.actor_id
   JOIN auth.sessions review_session ON review_session.id=basis.session_id AND review_session.user_id=basis.actor_id
   JOIN auth.sessions release_session ON release_session.id::text=auth.jwt()->>'session_id' AND release_session.user_id=auth.uid()
   WHERE a.workspace_id=p_workspace AND a.contract_id=p_contract AND a.contract_version=basis.source_version AND a.id=basis.artifact_id;
  IF deadline IS NULL OR deadline<=clock_timestamp() THEN status_name:='contract_review_required';
  ELSE
   status_name:='ready_for_human_review';
   candidate:=jsonb_build_object('basis_review_id',basis.id,'artifact_id',basis.artifact_id,'source_version',basis.source_version,
    'sha256',basis.sha256,'reviewed_at',basis.created_at,'policy_id',policy.id,
    'expected_sequence',(state->>'sequence')::integer,'max_expires_at',deadline);
  END IF;
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,
  'status',status_name,'candidate',candidate,'withdrawal',withdrawal,'current_review',state,'checked_at',checked,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.signature_review_candidate(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.signature_review_candidate(uuid,uuid,integer) TO authenticated;
CREATE FUNCTION public.signature_review_candidate(p_workspace uuid,p_contract uuid,p_version integer)
RETURNS jsonb LANGUAGE sql VOLATILE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.signature_review_candidate(p_workspace,p_contract,p_version) $$;
REVOKE ALL ON FUNCTION public.signature_review_candidate(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.signature_review_candidate(uuid,uuid,integer) TO authenticated;
COMMIT;
