-- Additive target dispatch in the existing private Storage authorization helper.
-- No public bucket, overwrite, delete, list or signed-URL permission is added.
-- Compensation: disable acquisition activation; preserve retained objects and audits.
-- Contract writes require the same exact current reservation used by the bounded transport.
BEGIN;
CREATE OR REPLACE FUNCTION private.acquisition_evidence_object_access(p_name text,p_upload boolean)
RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE artifact public.acquisition_evidence_artifacts%ROWTYPE; evidence_role text; stamped timestamptz:=clock_timestamp();
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR p_upload IS NULL OR p_name IS NULL OR p_name !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/[0-9a-f]{64}$' THEN RETURN false; END IF;
 -- Validate path before UUID casting; use the primary key then exact key equality.
 SELECT * INTO artifact FROM public.acquisition_evidence_artifacts a
 WHERE a.id=split_part(p_name,'/',2)::uuid
  AND p_name=a.workspace_id::text||'/'||a.id::text||'/'||a.expected_sha256;
 IF NOT FOUND OR artifact.created_at>stamped OR artifact.retain_until<=stamped THEN RETURN false; END IF;
 evidence_role:=private.acquisition_role(artifact.workspace_id);
 IF coalesce(evidence_role,'') NOT IN ('owner','admin','operator')
  OR (evidence_role='operator' AND artifact.created_by IS DISTINCT FROM auth.uid()) THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM auth.sessions s WHERE s.id::text=auth.jwt()->>'session_id'
  AND s.user_id=auth.uid() AND (s.not_after IS NULL OR s.not_after>stamped)) THEN RETURN false; END IF;
 IF EXISTS(SELECT 1 FROM public.acquisition_evidence_revocations r
  WHERE r.workspace_id=artifact.workspace_id AND r.artifact_id=artifact.id) THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_evidence_policies p
  WHERE p.id=artifact.retention_policy_id AND p.workspace_id=artifact.workspace_id AND p.purpose=artifact.purpose
   AND p.revoked_at IS NULL AND p.valid_from<=stamped AND p.valid_until>stamped) THEN RETURN false; END IF;
 IF NOT EXISTS(SELECT 1 FROM storage.buckets b WHERE b.id='acquisition-evidence' AND b.name=b.id
  AND b.public IS FALSE AND b.file_size_limit=10485760 AND b.type='STANDARD' AND b.versioning_status='DISABLED'
  AND b.lifecycle_configuration IS NULL AND b.allowed_mime_types=ARRAY['application/pdf','image/png','image/jpeg','text/plain']) THEN RETURN false; END IF;
 IF p_upload THEN
  RETURN artifact.created_by=auth.uid() AND storage.allow_only_operation('object.upload')
   AND EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled)
   AND (
    (artifact.campaign_id IS NOT NULL AND artifact.contract_id IS NULL AND artifact.contract_version IS NULL
     AND EXISTS(SELECT 1 FROM public.ad_campaigns c WHERE c.workspace_id=artifact.workspace_id
      AND c.id=artifact.campaign_id AND c.acquisition_channel='direct_mail' AND c.status='draft'))
    OR
    (artifact.campaign_id IS NULL AND artifact.contract_id IS NOT NULL AND artifact.contract_version IS NOT NULL
     AND EXISTS(SELECT 1 FROM public.deals d JOIN public.acquisition_contract_versions v
       ON v.workspace_id=d.workspace_id AND v.deal_id=d.id AND v.version=d.acquisition_version
      WHERE d.id=artifact.contract_id AND d.workspace_id=artifact.workspace_id
       AND d.acquisition_version=artifact.contract_version AND d.acquisition_status='draft' AND v.status='draft')
     AND EXISTS(SELECT 1 FROM private.acquisition_evidence_upload_slots slot
      WHERE slot.workspace_id=artifact.workspace_id AND slot.actor_id=auth.uid()
       AND slot.campaign_id IS NULL AND slot.contract_id=artifact.contract_id
       AND slot.contract_version=artifact.contract_version AND slot.artifact_id=artifact.id
       AND slot.started_at<=stamped AND slot.expires_at>stamped))
   );
 END IF;
 RETURN storage.allow_any_operation(ARRAY['object.get_authenticated','object.get_authenticated_info']);
END $$;
COMMIT;
