-- Additive contract targets in the existing evidence registry. No upload or review authority.
-- Compensation: disable acquisition activation; preserve artifacts, versions and audits.
BEGIN;
ALTER TABLE public.acquisition_contract_versions ADD CONSTRAINT acquisition_contract_version_scope UNIQUE(workspace_id,deal_id,version);
ALTER TABLE private.acquisition_evidence_policies DROP CONSTRAINT acquisition_evidence_policies_purpose_check,
 ADD CONSTRAINT acquisition_evidence_policies_purpose_check CHECK(purpose IN ('mail_content','mail_destination','purchase_contract','title_report','assignment_agreement','seller_disclosure','assignee_disclosure','closing_statement','supporting_document'));
ALTER TABLE public.acquisition_evidence_artifacts ALTER COLUMN campaign_id DROP NOT NULL,
 ADD COLUMN contract_id uuid, ADD COLUMN contract_version integer,
 DROP CONSTRAINT acquisition_evidence_artifacts_purpose_check,
 ADD CONSTRAINT acquisition_evidence_target CHECK(
  (campaign_id IS NOT NULL AND contract_id IS NULL AND contract_version IS NULL AND purpose IN ('mail_content','mail_destination')) OR
  (campaign_id IS NULL AND contract_id IS NOT NULL AND contract_version IS NOT NULL AND contract_version>0 AND purpose IN ('purchase_contract','title_report','assignment_agreement','seller_disclosure','assignee_disclosure','closing_statement','supporting_document'))),
 ADD CONSTRAINT acquisition_evidence_contract_version FOREIGN KEY(workspace_id,contract_id,contract_version)
  REFERENCES public.acquisition_contract_versions(workspace_id,deal_id,version),
 ADD CONSTRAINT acquisition_evidence_contract_identity UNIQUE(workspace_id,contract_id,contract_version,id);
CREATE INDEX acquisition_evidence_contract ON public.acquisition_evidence_artifacts(workspace_id,contract_id,contract_version,id) WHERE contract_id IS NOT NULL;
ALTER TABLE public.acquisition_evidence_revocations ALTER COLUMN campaign_id DROP NOT NULL,
 ADD COLUMN contract_id uuid, ADD COLUMN contract_version integer,
 ADD CONSTRAINT acquisition_revocation_target CHECK(
  (campaign_id IS NOT NULL AND contract_id IS NULL AND contract_version IS NULL) OR
  (campaign_id IS NULL AND contract_id IS NOT NULL AND contract_version IS NOT NULL AND contract_version>0)),
 ADD CONSTRAINT acquisition_revocation_contract FOREIGN KEY(workspace_id,contract_id,contract_version,artifact_id)
  REFERENCES public.acquisition_evidence_artifacts(workspace_id,contract_id,contract_version,id);

-- Internal lock helper: not executable by application roles. Definer entrypoints own authorization.
CREATE FUNCTION private.lock_contract_document_context(p_workspace uuid,p_contract uuid,p_version integer,p_roles text[])
RETURNS TABLE(actor_updated timestamptz,session_expires timestamptz)
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(private.acquisition_role(p_workspace),'')<>ALL(p_roles) THEN
  RAISE EXCEPTION 'Contract document authority required' USING ERRCODE='42501'; END IF;
 IF p_contract IS NULL OR p_version IS NULL OR p_version<1 THEN
  RAISE EXCEPTION 'Exact contract version required' USING ERRCODE='22023'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('deal-ref:'||p_contract::text,0));
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 SELECT m.updated_at,s.not_after INTO actor_updated,session_expires FROM public.workspace_memberships m
 JOIN public.profiles p ON p.id=m.user_id JOIN auth.sessions s ON s.user_id=p.id
 WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active' AND m.role=ANY(p_roles)
  AND p.status='approved' AND s.id::text=auth.jwt()->>'session_id'
  AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Contract document authority changed' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.deals d JOIN public.acquisition_contract_versions v ON v.deal_id=d.id AND v.workspace_id=d.workspace_id
 WHERE d.id=p_contract AND d.workspace_id=p_workspace AND v.version=p_version FOR SHARE OF d,v;
 IF NOT FOUND THEN RAISE EXCEPTION 'Contract version unavailable' USING ERRCODE='42501'; END IF;
 IF session_expires IS NOT NULL AND session_expires<=clock_timestamp() THEN
  RAISE EXCEPTION 'Contract document session expired' USING ERRCODE='42501'; END IF;
 RETURN NEXT;
END $$;
REVOKE ALL ON FUNCTION private.lock_contract_document_context(uuid,uuid,integer,text[]) FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.register_contract_document(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_purpose text,
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
 IF NOT EXISTS(SELECT 1 FROM public.deals WHERE id=p_contract AND workspace_id=p_workspace AND acquisition_version=p_version AND acquisition_status='draft') THEN
  RAISE EXCEPTION 'Current draft version required' USING ERRCODE='55000'; END IF;
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

CREATE FUNCTION private.revoke_contract_document(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_evidence_revocations%ROWTYPE; authority record; fingerprint text;
BEGIN
 IF p_id IS NULL OR p_artifact IS NULL OR p_reason IS NULL OR length(trim(p_reason)) NOT BETWEEN 20 AND 2000 THEN
  RAISE EXCEPTION 'Documented revocation required' USING ERRCODE='22023'; END IF;
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin']);
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-revocation:'||p_id::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||p_artifact::text,0));
 IF authority.session_expires IS NOT NULL AND authority.session_expires<=clock_timestamp() THEN
  RAISE EXCEPTION 'Document session expired' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND id=p_artifact AND campaign_id IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'Contract document unavailable' USING ERRCODE='42501'; END IF;
 fingerprint:=encode(sha256(convert_to(jsonb_build_array('contract_document',p_workspace,p_contract,p_version,p_artifact,p_reason,auth.uid())::text,'UTF8')),'hex');
 SELECT * INTO saved FROM public.acquisition_evidence_revocations WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Revocation request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('revocation_id',saved.id,'artifact_id',saved.artifact_id,'workspace_id',saved.workspace_id,'duplicate',true,'execution_authorized',false);
 END IF;
 INSERT INTO public.acquisition_evidence_revocations(id,workspace_id,contract_id,contract_version,artifact_id,reason,actor_id,actor_membership_updated_at,request_hash)
 VALUES(p_id,p_workspace,p_contract,p_version,p_artifact,p_reason,auth.uid(),authority.actor_updated,fingerprint) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_contract_document',p_artifact::text,'revoked',auth.uid()::text,p_workspace,
  jsonb_build_object('revocation_id',p_id,'contract_id',p_contract,'contract_version',p_version,'execution_authorized',false));
 RETURN jsonb_build_object('revocation_id',saved.id,'artifact_id',saved.artifact_id,'workspace_id',saved.workspace_id,'duplicate',false,'execution_authorized',false);
END $$;

CREATE FUNCTION private.contract_document_state(p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE a public.acquisition_evidence_artifacts%ROWTYPE; revoked timestamptz; policy_current boolean;
BEGIN
 IF auth.role() IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Contract document access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO a FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract
  AND contract_version=p_version AND id=p_artifact AND campaign_id IS NULL;
 IF NOT FOUND THEN RAISE EXCEPTION 'Contract document unavailable' USING ERRCODE='42501'; END IF;
 SELECT created_at INTO revoked FROM public.acquisition_evidence_revocations WHERE workspace_id=p_workspace AND artifact_id=p_artifact;
 SELECT revoked_at IS NULL AND valid_from<=statement_timestamp() AND valid_until>statement_timestamp() INTO policy_current
 FROM private.acquisition_evidence_policies WHERE id=a.retention_policy_id AND workspace_id=p_workspace AND purpose=a.purpose;
 RETURN jsonb_build_object('artifact_id',a.id,'workspace_id',a.workspace_id,'contract_id',a.contract_id,'contract_version',a.contract_version,
  'purpose',a.purpose,'expected_sha256',a.expected_sha256,'expected_byte_size',a.expected_byte_size,'media_type',a.media_type,
  'created_at',a.created_at,'retain_until',a.retain_until,'retention_policy_id',a.retention_policy_id,'revoked_at',revoked,
  'status',CASE WHEN revoked IS NOT NULL THEN 'revoked' WHEN a.retain_until<=statement_timestamp() THEN 'expired'
   WHEN policy_current IS DISTINCT FROM true THEN 'policy_review_required' ELSE 'pending_verification' END,
  'bytes_verified',false,'legal_review_approved',false,'execution_authorized',false,'checked_at',statement_timestamp());
END $$;
CREATE FUNCTION public.register_contract_document(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_purpose text,p_sha256 text,p_byte_size integer,p_media_type text,p_policy uuid,p_note text) RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.register_contract_document(p_id,p_workspace,p_contract,p_version,p_purpose,p_sha256,p_byte_size,p_media_type,p_policy,p_note) $$;
REVOKE ALL ON FUNCTION private.register_contract_document(uuid,uuid,uuid,integer,text,text,integer,text,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.register_contract_document(uuid,uuid,uuid,integer,text,text,integer,text,uuid,text) TO authenticated;
REVOKE ALL ON FUNCTION public.register_contract_document(uuid,uuid,uuid,integer,text,text,integer,text,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.register_contract_document(uuid,uuid,uuid,integer,text,text,integer,text,uuid,text) TO authenticated;
CREATE FUNCTION public.revoke_contract_document(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid,p_reason text) RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.revoke_contract_document(p_id,p_workspace,p_contract,p_version,p_artifact,p_reason) $$;
REVOKE ALL ON FUNCTION private.revoke_contract_document(uuid,uuid,uuid,integer,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.revoke_contract_document(uuid,uuid,uuid,integer,uuid,text) TO authenticated;
REVOKE ALL ON FUNCTION public.revoke_contract_document(uuid,uuid,uuid,integer,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.revoke_contract_document(uuid,uuid,uuid,integer,uuid,text) TO authenticated;
CREATE FUNCTION public.contract_document_state(p_workspace uuid,p_contract uuid,p_version integer,p_artifact uuid) RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.contract_document_state(p_workspace,p_contract,p_version,p_artifact) $$;
REVOKE ALL ON FUNCTION private.contract_document_state(uuid,uuid,integer,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.contract_document_state(uuid,uuid,integer,uuid) TO authenticated;
REVOKE ALL ON FUNCTION public.contract_document_state(uuid,uuid,integer,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION public.contract_document_state(uuid,uuid,integer,uuid) TO authenticated;
-- Existing Storage upload helper still requires a draft mail campaign. Contract uploads
-- therefore remain denied until aggregate admission and the complete upload path are implemented.
COMMIT;
