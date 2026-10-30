-- Read-only owner/admin choice for the existing content review. Never approval authority.
BEGIN;
CREATE FUNCTION private.acquisition_evidence_review_candidate(p_workspace uuid,p_campaign uuid,p_artifact uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE artifact public.acquisition_evidence_artifacts%ROWTYPE; observation public.acquisition_evidence_verifications%ROWTYPE;
 deadline timestamptz; checked timestamptz:=statement_timestamp();
BEGIN
 IF auth.jwt()->>'role' IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') THEN
  RAISE EXCEPTION 'Content reviewer with MFA required' USING ERRCODE='42501'; END IF;
 SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND campaign_id=p_campaign AND id=p_artifact;
 IF NOT FOUND OR artifact.purpose<>'mail_content' THEN RAISE EXCEPTION 'Review file unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO observation FROM public.acquisition_evidence_verifications
  WHERE workspace_id=p_workspace AND campaign_id=p_campaign AND artifact_id=p_artifact ORDER BY created_at DESC,id DESC LIMIT 1;
 IF NOT FOUND OR NOT private.acquisition_content_evidence_current(p_workspace,p_campaign,p_artifact,artifact.expected_sha256,observation.id,checked) THEN
  RAISE EXCEPTION 'Current verified file required' USING ERRCODE='55000'; END IF;
 SELECT least(artifact.retain_until,policy.valid_until,k.valid_until,session.not_after) INTO deadline
  FROM private.acquisition_evidence_verification_keys k
  JOIN private.acquisition_evidence_policies policy ON policy.id=artifact.retention_policy_id AND policy.workspace_id=p_workspace
  JOIN auth.sessions session ON session.id=observation.session_id AND session.user_id=observation.actor_id
  WHERE k.id=observation.key_id AND k.workspace_id=p_workspace;
 IF deadline IS NULL OR deadline<=checked THEN RAISE EXCEPTION 'Review file expired' USING ERRCODE='55000'; END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'campaign_id',p_campaign,'artifact_id',p_artifact,
  'sha256',artifact.expected_sha256,'verification_id',observation.id,'status','review_candidate',
  'max_approval_until',deadline,'checked_at',checked,'preview_authorized',false,'content_approved',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.acquisition_evidence_review_candidate(p_workspace uuid,p_campaign uuid,p_artifact uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.acquisition_evidence_review_candidate(p_workspace,p_campaign,p_artifact)
$$;
REVOKE ALL ON FUNCTION private.acquisition_evidence_review_candidate(uuid,uuid,uuid),
 public.acquisition_evidence_review_candidate(uuid,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_evidence_review_candidate(uuid,uuid,uuid),
 public.acquisition_evidence_review_candidate(uuid,uuid,uuid) TO authenticated;
COMMIT;
