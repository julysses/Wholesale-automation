-- Read-only current scan assessment. No preview, clearance or approval authority.
BEGIN;
CREATE INDEX acquisition_evidence_detected_bytes
 ON public.acquisition_evidence_verifications(workspace_id,(observation->>'sha256')) WHERE scan_status='detected';
CREATE FUNCTION private.acquisition_evidence_scan_state(p_workspace uuid,p_campaign uuid,p_artifact uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE artifact public.acquisition_evidence_artifacts%ROWTYPE;
 latest public.acquisition_evidence_verifications%ROWTYPE; registry jsonb;
 role_name text; quarantine boolean; current_scan boolean:=false; status_name text; checked timestamptz:=statement_timestamp();
BEGIN
 role_name:=private.acquisition_role(p_workspace);
 IF auth.jwt()->>'role' IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(role_name,'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Evidence scan access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO artifact FROM public.acquisition_evidence_artifacts
  WHERE workspace_id=p_workspace AND campaign_id=p_campaign AND id=p_artifact;
 IF NOT FOUND OR (role_name='operator' AND artifact.created_by<>auth.uid()) THEN
  RAISE EXCEPTION 'Evidence scan unavailable' USING ERRCODE='42501'; END IF;
 registry:=private.acquisition_evidence_state(p_workspace,p_campaign,p_artifact);
 -- A later clean scan or re-registration of the same bytes cannot erase detection.
 -- Do not expose another artifact's identity, scan payload or signer information.
 SELECT EXISTS(SELECT 1 FROM public.acquisition_evidence_verifications
  WHERE workspace_id=p_workspace AND scan_status='detected' AND observation->>'sha256'=artifact.expected_sha256) INTO quarantine;
 SELECT * INTO latest FROM public.acquisition_evidence_verifications
  WHERE workspace_id=p_workspace AND campaign_id=p_campaign AND artifact_id=p_artifact
  ORDER BY created_at DESC,id DESC LIMIT 1;
 IF latest.id IS NOT NULL AND latest.scan_status='no_detection' AND latest.created_at<=checked THEN
  SELECT EXISTS(SELECT 1 FROM private.acquisition_evidence_verification_keys k
   JOIN public.workspace_memberships m ON m.workspace_id=k.workspace_id AND m.user_id=latest.actor_id
   JOIN public.profiles p ON p.id=m.user_id
   JOIN auth.sessions s ON s.id=latest.session_id AND s.user_id=m.user_id
   WHERE k.id=latest.key_id AND k.workspace_id=p_workspace AND k.revoked_at IS NULL
    AND k.valid_from<=checked AND checked<k.valid_until
    AND k.valid_from<=(latest.observation->>'checked_at')::timestamptz
    AND k.scanner_version=latest.observation->>'scanner_version'
    AND k.scan_policy_version=latest.observation->>'scan_policy_version'
    AND m.status='active' AND m.role IN ('owner','admin','operator')
    AND m.updated_at=latest.actor_membership_updated_at AND p.status='approved'
    AND (s.not_after IS NULL OR s.not_after>checked)) INTO current_scan;
 END IF;
 status_name:=CASE WHEN registry->>'status'<>'pending_verification' THEN registry->>'status'
  WHEN quarantine THEN 'quarantined' WHEN latest.id IS NULL THEN 'not_scanned'
  WHEN current_scan THEN 'no_detection_observed' ELSE 'requires_review' END;
 RETURN jsonb_build_object('workspace_id',p_workspace,'campaign_id',p_campaign,'artifact_id',p_artifact,
  'status',status_name,'quarantined',quarantine,
  'observation_id',CASE WHEN status_name='no_detection_observed' THEN latest.id ELSE NULL END,
  'preview_authorized',false,'content_approved',false,'execution_authorized',false,'checked_at',checked);
END $$;
CREATE FUNCTION public.acquisition_evidence_scan_state(p_workspace uuid,p_campaign uuid,p_artifact uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.acquisition_evidence_scan_state(p_workspace,p_campaign,p_artifact)
$$;
REVOKE ALL ON FUNCTION private.acquisition_evidence_scan_state(uuid,uuid,uuid),
 public.acquisition_evidence_scan_state(uuid,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_evidence_scan_state(uuid,uuid,uuid),
 public.acquisition_evidence_scan_state(uuid,uuid,uuid) TO authenticated;
COMMIT;
