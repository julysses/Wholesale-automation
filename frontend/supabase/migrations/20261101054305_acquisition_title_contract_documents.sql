-- Extend existing original-document capture to the current title-review version.
-- File classification/upload does not prove clear title, legal ownership or disposition authority.
-- Existing exact retries, retention, capacity, tenant/session and Storage operation
-- guards remain intact. No term edits, lifecycle writes or reviewer policies added.
-- Compensation: pause acquisition uploads/activation while retaining evidence/history.
BEGIN;
CREATE OR REPLACE FUNCTION private.register_contract_document(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_purpose text,
 p_sha256 text,p_byte_size integer,p_media_type text,p_policy uuid,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_evidence_artifacts%ROWTYPE; policy private.acquisition_evidence_policies%ROWTYPE;
 authority record; fingerprint text; stamped timestamptz; active boolean;
BEGIN
 IF p_id IS NULL OR p_purpose IS NULL OR p_purpose NOT IN ('purchase_contract','title_report','assignment_agreement','seller_disclosure','assignee_disclosure','closing_statement','supporting_document')
  OR p_sha256 IS NULL OR p_sha256 !~ '^[0-9a-f]{64}$' OR p_byte_size IS NULL OR p_byte_size NOT BETWEEN 1 AND 10485760
  OR p_media_type IS NULL OR p_media_type NOT IN ('application/pdf','image/png','image/jpeg','text/plain')
  OR p_policy IS NULL OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 20 AND 2000 THEN
  RAISE EXCEPTION 'Bounded document expectations required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin','operator']);
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||p_id::text,0));
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN
  RAISE EXCEPTION 'Document session expired' USING ERRCODE='42501'; END IF;
 fingerprint:=encode(sha256(convert_to(jsonb_build_array('contract_document',p_workspace,p_contract,p_version,p_purpose,p_sha256,p_byte_size,p_media_type,p_policy,p_note,auth.uid())::text,'UTF8')),'hex');
 SELECT * INTO saved FROM public.acquisition_evidence_artifacts WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint OR saved.contract_id IS DISTINCT FROM p_contract
   OR saved.contract_version IS DISTINCT FROM p_version OR saved.campaign_id IS NOT NULL THEN
   RAISE EXCEPTION 'Document request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('artifact_id',saved.id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,
   'contract_version',saved.contract_version,'retain_until',saved.retain_until,'duplicate',true,'bytes_verified',false,'execution_authorized',false);
 END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.deals WHERE id=p_contract AND workspace_id=p_workspace AND acquisition_version=p_version AND acquisition_status IN ('draft','pending_signature','title_review')) THEN
  RAISE EXCEPTION 'Current document-capture version required' USING ERRCODE='55000'; END IF;
 SELECT * INTO policy FROM private.acquisition_evidence_policies WHERE id=p_policy AND workspace_id=p_workspace AND purpose=p_purpose FOR SHARE;
 stamped:=clock_timestamp();
 IF policy.id IS NULL OR policy.revoked_at IS NOT NULL OR NOT(policy.valid_from<=stamped AND stamped<policy.valid_until) THEN
  RAISE EXCEPTION 'Reviewed retention policy required' USING ERRCODE='55000'; END IF;
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=stamped THEN
  RAISE EXCEPTION 'Document session expired' USING ERRCODE='42501'; END IF;
 INSERT INTO public.acquisition_evidence_artifacts(id,workspace_id,contract_id,contract_version,purpose,expected_sha256,expected_byte_size,
  media_type,retention_policy_id,retain_until,provenance_note,created_by,actor_membership_updated_at,created_at,request_hash)
 VALUES(p_id,p_workspace,p_contract,p_version,p_purpose,p_sha256,p_byte_size,p_media_type,p_policy,
  stamped+make_interval(secs=>policy.retention_seconds),p_note,auth.uid(),authority.actor_updated,stamped,fingerprint) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_contract_document',p_id::text,'registered',auth.uid()::text,p_workspace,
  jsonb_build_object('contract_id',p_contract,'contract_version',p_version,'purpose',p_purpose,'policy_id',p_policy,'bytes_verified',false,'execution_authorized',false));
 RETURN jsonb_build_object('artifact_id',saved.id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,
  'contract_version',saved.contract_version,'retain_until',saved.retain_until,'duplicate',false,'bytes_verified',false,'execution_authorized',false);
END $$;

CREATE OR REPLACE FUNCTION private.admit_contract_document_upload(p_attempt uuid,p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid,p_purpose text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE stamped timestamptz; chosen smallint; retry_at timestamptz; expiry timestamptz;
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Evidence upload authority required' USING ERRCODE='42501'; END IF;
 IF p_attempt IS NULL OR p_contract IS NULL OR p_version IS NULL OR p_version<1 OR p_artifact IS NULL OR p_purpose IS NULL
  OR p_purpose NOT IN ('purchase_contract','title_report','assignment_agreement','seller_disclosure','assignee_disclosure','closing_statement','supporting_document') THEN
  RAISE EXCEPTION 'Evidence upload identity required' USING ERRCODE='22023'; END IF;
 -- Across API processes. No client release or early reuse of a reservation.
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-upload-admission:'||p_workspace::text,0));
 stamped:=clock_timestamp();
 -- Fresh post-wait authority and deadlines; matching phone/email/token claims are insufficient.
 PERFORM 1 FROM public.acquisition_evidence_artifacts a
 JOIN private.acquisition_evidence_policies p ON p.id=a.retention_policy_id AND p.workspace_id=a.workspace_id AND p.purpose=a.purpose
 JOIN public.deals c ON c.id=a.contract_id AND c.workspace_id=a.workspace_id
 JOIN public.acquisition_contract_versions v ON v.deal_id=c.id AND v.workspace_id=c.workspace_id AND v.version=a.contract_version
 JOIN public.workspaces w ON w.id=a.workspace_id
 JOIN public.workspace_memberships m ON m.workspace_id=w.id AND m.user_id=auth.uid()
 JOIN public.profiles profile ON profile.id=m.user_id
 JOIN auth.sessions s ON s.user_id=profile.id AND s.id::text=auth.jwt()->>'session_id'
 WHERE a.id=p_artifact AND a.workspace_id=p_workspace AND a.contract_id=p_contract AND a.contract_version=p_version AND a.purpose=p_purpose
  AND a.created_by=auth.uid() AND a.created_at<=stamped AND a.retain_until>stamped
  AND p.revoked_at IS NULL AND p.valid_from<=stamped AND p.valid_until>stamped
  AND c.acquisition_status IN ('draft','pending_signature','title_review') AND c.acquisition_version=p_version AND w.status='active'
  AND m.status='active' AND m.role IN ('owner','admin','operator') AND profile.status='approved'
  AND (s.not_after IS NULL OR s.not_after>stamped)
  AND EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled)
  AND NOT EXISTS(SELECT 1 FROM public.acquisition_evidence_revocations r WHERE r.workspace_id=a.workspace_id AND r.artifact_id=a.id);
 IF NOT FOUND THEN RAISE EXCEPTION 'Current evidence upload authority required' USING ERRCODE='42501'; END IF;
 IF EXISTS(SELECT 1 FROM private.acquisition_evidence_upload_slots WHERE attempt_id=p_attempt) THEN
  RAISE EXCEPTION 'A fresh upload attempt is required' USING ERRCODE='23505'; END IF;
 SELECT expires_at INTO retry_at FROM private.acquisition_evidence_upload_slots
  WHERE workspace_id=p_workspace AND actor_id=auth.uid() AND expires_at>stamped;
 IF retry_at IS NULL THEN
  SELECT n::smallint INTO chosen FROM generate_series(1,2) n WHERE NOT EXISTS(
   SELECT 1 FROM private.acquisition_evidence_upload_slots WHERE workspace_id=p_workspace AND slot=n AND expires_at>stamped)
   ORDER BY n LIMIT 1;
  IF chosen IS NULL THEN SELECT min(expires_at) INTO retry_at FROM private.acquisition_evidence_upload_slots WHERE workspace_id=p_workspace; END IF;
 END IF;
 IF retry_at IS NULL THEN
  expiry:=stamped+interval '120 seconds';
  INSERT INTO private.acquisition_evidence_upload_slots(workspace_id,slot,actor_id,attempt_id,campaign_id,contract_id,contract_version,artifact_id,started_at,expires_at)
   VALUES(p_workspace,chosen,auth.uid(),p_attempt,NULL,p_contract,p_version,p_artifact,stamped,expiry)
   ON CONFLICT(workspace_id,slot) DO UPDATE SET actor_id=EXCLUDED.actor_id,attempt_id=EXCLUDED.attempt_id,
    campaign_id=NULL,contract_id=EXCLUDED.contract_id,contract_version=EXCLUDED.contract_version,artifact_id=EXCLUDED.artifact_id,started_at=EXCLUDED.started_at,expires_at=EXCLUDED.expires_at;
 END IF;
 RETURN jsonb_build_object('attempt_id',p_attempt,'workspace_id',p_workspace,'contract_id',p_contract,'contract_version',p_version,'artifact_id',p_artifact,
  'purpose',p_purpose,'admitted',retry_at IS NULL,'checked_at',stamped,'expires_at',expiry,
  'retry_after_seconds',CASE WHEN retry_at IS NULL THEN 0 ELSE greatest(1,ceil(extract(epoch FROM retry_at-stamped))::integer) END,
  'execution_authorized',false);
END $$;

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
       AND d.acquisition_version=artifact.contract_version AND d.acquisition_status IN ('draft','pending_signature','title_review') AND v.status='draft')
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
