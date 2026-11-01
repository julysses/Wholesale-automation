-- Read-only choices. The writer independently checks all findings and authority.
-- No policy is provisioned and no review, transition or transaction is executed.
-- Compensation: pause acquisition or revoke policy; preserve original history.
BEGIN;
CREATE FUNCTION private.disposition_source_choice(p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid,p_scan uuid,p_at timestamptz)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY INVOKER SET search_path='' AS $$
DECLARE ref record; artifact public.acquisition_evidence_artifacts%ROWTYPE;
 scan public.acquisition_evidence_verifications%ROWTYPE; deadline timestamptz;
BEGIN
 IF p_at IS NULL OR NOT isfinite(p_at) OR p_artifact IS NULL THEN RETURN NULL; END IF;
 SELECT * INTO ref FROM private.contract_document_reference(p_workspace,p_contract,p_version,p_artifact);
 IF NOT FOUND OR ref.link_revoked THEN RETURN NULL; END IF;
 SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=ref.source_version AND id=p_artifact AND campaign_id IS NULL;
 IF NOT FOUND THEN RETURN NULL; END IF;
 SELECT * INTO scan FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=p_artifact ORDER BY created_at DESC,id DESC LIMIT 1;
 IF NOT FOUND OR (p_scan IS NOT NULL AND scan.id<>p_scan) OR NOT private.contract_review_evidence_current(
  p_workspace,p_contract,ref.source_version,p_artifact,scan.id,artifact.expected_sha256,artifact.purpose,p_at) THEN RETURN NULL; END IF;
 SELECT least(artifact.retain_until,rp.valid_until,k.valid_until,ks.valid_until,s.not_after) INTO deadline
 FROM private.acquisition_evidence_policies rp
 JOIN private.acquisition_evidence_verification_keys k ON k.workspace_id=rp.workspace_id AND k.id=scan.key_id
 JOIN private.acquisition_contract_verification_key_scopes ks ON ks.workspace_id=k.workspace_id AND ks.key_id=k.id AND ks.purpose=artifact.purpose
 JOIN auth.sessions s ON s.id=scan.session_id AND s.user_id=scan.actor_id
 WHERE rp.workspace_id=p_workspace AND rp.id=artifact.retention_policy_id;
 IF deadline IS NULL OR deadline<=p_at THEN RETURN NULL; END IF;
 RETURN jsonb_build_object('artifact_id',artifact.id,'source_version',ref.source_version,'verification_id',scan.id,
  'sha256',artifact.expected_sha256,'purpose',artifact.purpose,'expires_at',deadline);
END $$;
REVOKE ALL ON FUNCTION private.disposition_source_choice(uuid,uuid,integer,uuid,uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.disposition_review_candidate(p_workspace uuid,p_contract uuid,p_version integer)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE checked timestamptz:=statement_timestamp(); state jsonb; status_name text;
 prior public.acquisition_contract_reviews%ROWTYPE; title public.acquisition_contract_reviews%ROWTYPE;
 executed public.acquisition_contract_reviews%ROWTYPE; execution public.acquisition_contract_transitions%ROWTYPE;
 plan public.acquisition_disposition_plans%ROWTYPE; policy private.acquisition_contract_review_policies%ROWTYPE;
 scope private.acquisition_disposition_policy_scopes%ROWTYPE; root jsonb; legal jsonb;
 deadline timestamptz; approval_deadline timestamptz; reviewer_expires timestamptz;
 candidate jsonb:=NULL; resolution jsonb:=NULL; withdrawal jsonb:=NULL;
BEGIN
 state:=private.disposition_review_state(p_workspace,p_contract,p_version);
 SELECT * INTO prior FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='disposition_findings' ORDER BY sequence DESC LIMIT 1;
 IF prior.status IN ('approved','requires_resolution') AND prior.actor_id=auth.uid() AND prior.sequence<2147483647 THEN
  withdrawal:=jsonb_build_object('review_id',prior.id,'plan_id',prior.disposition_plan_id,'exit_type',prior.disposition_exit_type,
   'policy_id',prior.policy_id,'expected_sequence',prior.sequence,'original_status',prior.status);
 END IF;
 SELECT * INTO plan FROM public.acquisition_disposition_plans WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version ORDER BY sequence DESC LIMIT 1;
 SELECT * INTO execution FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=plan.execution_transition_id AND recorded_status='executed';
 SELECT * INTO executed FROM public.acquisition_contract_reviews WHERE id=execution.execution_review_id;
 SELECT * INTO title FROM public.acquisition_contract_reviews WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND kind='title_findings' ORDER BY sequence DESC LIMIT 1;
 SELECT p.* INTO policy FROM private.acquisition_contract_review_policies p
 JOIN private.acquisition_disposition_policy_scopes s ON s.policy_id=p.id AND s.workspace_id=p.workspace_id AND s.reviewer_id=p.reviewer_id
 WHERE p.workspace_id=p_workspace AND p.reviewer_id=auth.uid() AND s.exit_type=plan.exit_type
  AND private.disposition_policy_current(p_workspace,p.id,auth.uid(),plan.exit_type,checked,jsonb_build_object('reviewer',to_jsonb(p),'scope',to_jsonb(s)))
 ORDER BY p.valid_from DESC,p.id DESC LIMIT 1;
 SELECT * INTO scope FROM private.acquisition_disposition_policy_scopes WHERE policy_id=policy.id;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled) THEN status_name:='paused';
 ELSIF NOT EXISTS(SELECT 1 FROM public.deals WHERE workspace_id=p_workspace AND id=p_contract AND acquisition_version=p_version AND acquisition_status='title_review') THEN status_name:='contract_unavailable';
 ELSIF coalesce(prior.sequence,0)>=2147483647 THEN status_name:='history_limit_reached';
 ELSIF plan.id IS NULL OR plan.status<>'proposed' THEN status_name:='proposal_required';
 ELSIF execution.id IS NULL OR executed.id IS NULL OR executed.kind<>'executed_contract' OR executed.status<>'approved'
  OR executed.purpose<>'purchase_contract' OR NOT EXISTS(SELECT 1 FROM public.acquisition_contract_transitions WHERE workspace_id=p_workspace
   AND contract_id=p_contract AND contract_version=p_version AND id=plan.title_entry_id AND recorded_status='title_review'
   AND execution_review_id=execution.execution_review_id) THEN status_name:='contract_unavailable';
 ELSIF title.id IS NULL OR title.status NOT IN ('approved','requires_resolution') OR title.title_execution_transition_id<>execution.id THEN status_name:='title_findings_required';
 ELSIF policy.id IS NULL THEN status_name:='reviewer_policy_required';
 ELSE
  root:=private.disposition_source_choice(p_workspace,p_contract,p_version,executed.artifact_id,executed.verification_id,checked);
  IF root IS NULL OR root->>'sha256'<>executed.sha256 OR (root->>'source_version')::integer<>executed.source_version THEN status_name:='evidence_review_required';
  ELSE
   IF scope.legal_source_id IS NOT NULL THEN
    legal:=private.disposition_source_choice(p_workspace,p_contract,p_version,scope.legal_source_id,
     CASE WHEN scope.legal_source_id=executed.artifact_id THEN executed.verification_id END,checked);
   END IF;
   SELECT not_after INTO reviewer_expires FROM auth.sessions WHERE id=(auth.jwt()->>'session_id')::uuid AND user_id=auth.uid();
   deadline:=least((root->>'expires_at')::timestamptz,policy.valid_until,scope.valid_until,reviewer_expires,checked+make_interval(secs=>policy.max_review_seconds));
   IF deadline IS NULL OR deadline<=checked THEN status_name:='evidence_review_required';
   ELSE
    resolution:=jsonb_build_object('plan_id',plan.id,'exit_type',plan.exit_type,'policy_id',policy.id,
     'execution_transition_id',execution.id,'title_entry_id',plan.title_entry_id,'title_review_id',title.id,'title_status',title.status,
     'expected_sequence',(state->>'sequence')::integer,'available_until',deadline,'executed_source',root,'legal_source',legal);
    IF NOT private.execution_review_current(executed.id,checked) THEN status_name:='execution_review_required';
    ELSIF NOT private.title_review_current(title.id,checked) THEN status_name:='title_review_required';
    ELSIF plan.exit_type='wholesale_assignment' AND legal IS NULL THEN status_name:='legal_evidence_required';
    ELSE
     approval_deadline:=least(deadline,executed.expires_at,title.expires_at,(legal->>'expires_at')::timestamptz);
     IF approval_deadline<=checked THEN status_name:='title_review_required';
     ELSE
      status_name:='ready_for_human_review';candidate:=resolution||jsonb_build_object('max_expires_at',approval_deadline);
     END IF;
    END IF;
   END IF;
  END IF;
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,
  'status',status_name,'candidate',candidate,'resolution',resolution,'withdrawal',withdrawal,
  'current_review',state,'checked_at',checked,'execution_authorized',false);
END $$;
REVOKE ALL ON FUNCTION private.disposition_review_candidate(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.disposition_review_candidate(uuid,uuid,integer) TO authenticated;
CREATE FUNCTION public.disposition_review_candidate(p_workspace uuid,p_contract uuid,p_version integer) RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.disposition_review_candidate(p_workspace,p_contract,p_version) $$;
REVOKE ALL ON FUNCTION public.disposition_review_candidate(uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.disposition_review_candidate(uuid,uuid,integer) TO authenticated;
COMMIT;
