-- Shared operational capacity for mail and version-bound contract documents.
-- No Storage upload, legal approval or execution authority is granted.
-- Compensation: disable acquisition activation, preserve slots and evidence;
-- reservations expire after 120 seconds. Do not drop populated target columns.
BEGIN;
ALTER TABLE private.acquisition_evidence_upload_slots
 ALTER COLUMN campaign_id DROP NOT NULL,
 ADD COLUMN contract_id uuid,
 ADD COLUMN contract_version integer,
 ADD CONSTRAINT acquisition_upload_slot_target CHECK(
  (campaign_id IS NOT NULL AND contract_id IS NULL AND contract_version IS NULL) OR
  (campaign_id IS NULL AND contract_id IS NOT NULL AND contract_version IS NOT NULL AND contract_version>0)),
 ADD CONSTRAINT acquisition_upload_slot_contract FOREIGN KEY(workspace_id,contract_id,contract_version,artifact_id)
  REFERENCES public.acquisition_evidence_artifacts(workspace_id,contract_id,contract_version,id);
-- Retain the same private RLS table, two workspace slots, actor cap and advisory lock.
-- Clear the alternate target when an expired slot is reused in either direction.
CREATE OR REPLACE FUNCTION private.admit_acquisition_evidence_upload(p_attempt uuid,p_workspace uuid,p_campaign uuid,p_artifact uuid,p_purpose text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE stamped timestamptz; chosen smallint; retry_at timestamptz; expiry timestamptz;
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Evidence upload authority required' USING ERRCODE='42501'; END IF;
 IF p_attempt IS NULL OR p_campaign IS NULL OR p_artifact IS NULL OR p_purpose IS NULL
  OR p_purpose NOT IN ('mail_content','mail_destination') THEN
  RAISE EXCEPTION 'Evidence upload identity required' USING ERRCODE='22023'; END IF;
 -- Across API processes. No client release or early reuse of a reservation.
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-upload-admission:'||p_workspace::text,0));
 stamped:=clock_timestamp();
 -- Fresh post-wait authority and deadlines; matching phone/email/token claims are insufficient.
 PERFORM 1 FROM public.acquisition_evidence_artifacts a
 JOIN private.acquisition_evidence_policies p ON p.id=a.retention_policy_id AND p.workspace_id=a.workspace_id AND p.purpose=a.purpose
 JOIN public.ad_campaigns c ON c.id=a.campaign_id AND c.workspace_id=a.workspace_id
 JOIN public.workspaces w ON w.id=a.workspace_id
 JOIN public.workspace_memberships m ON m.workspace_id=w.id AND m.user_id=auth.uid()
 JOIN public.profiles profile ON profile.id=m.user_id
 JOIN auth.sessions s ON s.user_id=profile.id AND s.id::text=auth.jwt()->>'session_id'
 WHERE a.id=p_artifact AND a.workspace_id=p_workspace AND a.campaign_id=p_campaign AND a.purpose=p_purpose
  AND a.created_by=auth.uid() AND a.created_at<=stamped AND a.retain_until>stamped
  AND p.revoked_at IS NULL AND p.valid_from<=stamped AND p.valid_until>stamped
  AND c.acquisition_channel='direct_mail' AND c.status='draft' AND w.status='active'
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
  INSERT INTO private.acquisition_evidence_upload_slots(workspace_id,slot,actor_id,attempt_id,campaign_id,artifact_id,started_at,expires_at)
   VALUES(p_workspace,chosen,auth.uid(),p_attempt,p_campaign,p_artifact,stamped,expiry)
   ON CONFLICT(workspace_id,slot) DO UPDATE SET actor_id=EXCLUDED.actor_id,attempt_id=EXCLUDED.attempt_id,
    contract_id=NULL,contract_version=NULL,campaign_id=EXCLUDED.campaign_id,artifact_id=EXCLUDED.artifact_id,started_at=EXCLUDED.started_at,expires_at=EXCLUDED.expires_at;
 END IF;
 RETURN jsonb_build_object('attempt_id',p_attempt,'workspace_id',p_workspace,'campaign_id',p_campaign,'artifact_id',p_artifact,
  'purpose',p_purpose,'admitted',retry_at IS NULL,'checked_at',stamped,'expires_at',expiry,
  'retry_after_seconds',CASE WHEN retry_at IS NULL THEN 0 ELSE greatest(1,ceil(extract(epoch FROM retry_at-stamped))::integer) END,
  'execution_authorized',false);
END $$;
CREATE FUNCTION private.admit_contract_document_upload(p_attempt uuid,p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid,p_purpose text)
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
  AND c.acquisition_status='draft' AND c.acquisition_version=p_version AND w.status='active'
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
CREATE FUNCTION public.admit_contract_document_upload(p_attempt uuid,p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid,p_purpose text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.admit_contract_document_upload(p_attempt,p_workspace,p_contract,p_version,p_artifact,p_purpose)
$$;
REVOKE ALL ON FUNCTION private.admit_contract_document_upload(uuid,uuid,uuid,integer,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.admit_contract_document_upload(uuid,uuid,uuid,integer,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.admit_contract_document_upload(uuid,uuid,uuid,integer,uuid,text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.admit_contract_document_upload(uuid,uuid,uuid,integer,uuid,text) TO authenticated;
COMMIT;
