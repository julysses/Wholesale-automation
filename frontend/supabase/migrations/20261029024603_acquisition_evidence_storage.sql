-- Local proposal only. Requires the protected registry; grants no review/execution authority.
BEGIN;
-- Fail on collision instead of adopting an unknown bucket or changing its visibility.
INSERT INTO storage.buckets(id,name,public,file_size_limit,allowed_mime_types)
VALUES('acquisition-evidence','acquisition-evidence',false,10485760,
 ARRAY['application/pdf','image/png','image/jpeg','text/plain']);

CREATE FUNCTION private.acquisition_evidence_object_access(p_name text,p_upload boolean)
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
   AND EXISTS(SELECT 1 FROM public.ad_campaigns c WHERE c.workspace_id=artifact.workspace_id
    AND c.id=artifact.campaign_id AND c.acquisition_channel='direct_mail' AND c.status='draft');
 END IF;
 RETURN storage.allow_any_operation(ARRAY['object.get_authenticated','object.get_authenticated_info']);
END $$;
REVOKE ALL ON FUNCTION private.acquisition_evidence_object_access(text,boolean) FROM PUBLIC,anon,authenticated,service_role;
-- PostgreSQL checks policy function EXECUTE before evaluating CASE. Anonymous
-- callers need this one helper privilege; its first check returns false for them.
-- No private schema/table grants or public RPC wrapper are added.
GRANT EXECUTE ON FUNCTION private.acquisition_evidence_object_access(text,boolean) TO anon,authenticated;

-- Restrictive guards also contain unrelated broad permissive policies.
CREATE POLICY acquisition_evidence_read_guard ON storage.objects AS RESTRICTIVE FOR SELECT TO PUBLIC
 USING(CASE WHEN bucket_id='acquisition-evidence' THEN
  CASE WHEN (SELECT auth.role())='authenticated' THEN
   archived_at IS NULL AND NOT is_delete_marker AND NOT is_versioned AND private.acquisition_evidence_object_access(name,false) ELSE false END
  ELSE true END);
CREATE POLICY acquisition_evidence_upload_guard ON storage.objects AS RESTRICTIVE FOR INSERT TO PUBLIC
 WITH CHECK(CASE WHEN bucket_id='acquisition-evidence' THEN
  CASE WHEN (SELECT auth.role())='authenticated' THEN
   archived_at IS NULL AND NOT is_delete_marker AND NOT is_versioned AND private.acquisition_evidence_object_access(name,true) ELSE false END
  ELSE true END);
CREATE POLICY acquisition_evidence_read ON storage.objects FOR SELECT TO authenticated
 USING(bucket_id='acquisition-evidence' AND private.acquisition_evidence_object_access(name,false));
CREATE POLICY acquisition_evidence_upload ON storage.objects FOR INSERT TO authenticated
 WITH CHECK(bucket_id='acquisition-evidence' AND private.acquisition_evidence_object_access(name,true));
CREATE POLICY acquisition_evidence_no_replace ON storage.objects AS RESTRICTIVE FOR UPDATE TO PUBLIC
 USING(bucket_id IS DISTINCT FROM 'acquisition-evidence') WITH CHECK(bucket_id IS DISTINCT FROM 'acquisition-evidence');
CREATE POLICY acquisition_evidence_no_delete ON storage.objects AS RESTRICTIVE FOR DELETE TO PUBLIC
 USING(bucket_id IS DISTINCT FROM 'acquisition-evidence');
CREATE POLICY acquisition_evidence_bucket_no_insert ON storage.buckets AS RESTRICTIVE FOR INSERT TO PUBLIC
 WITH CHECK(id<>'acquisition-evidence' AND name<>'acquisition-evidence');
CREATE POLICY acquisition_evidence_bucket_no_update ON storage.buckets AS RESTRICTIVE FOR UPDATE TO PUBLIC
 USING(id<>'acquisition-evidence' AND name<>'acquisition-evidence')
 WITH CHECK(id<>'acquisition-evidence' AND name<>'acquisition-evidence');
CREATE POLICY acquisition_evidence_bucket_no_delete ON storage.buckets AS RESTRICTIVE FOR DELETE TO PUBLIC
 USING(id<>'acquisition-evidence' AND name<>'acquisition-evidence');
-- Service-role/platform owners bypass RLS. Never expose those credentials or use
-- them for the application evidence path. Bytes and scanning remain unverified.
COMMIT;
