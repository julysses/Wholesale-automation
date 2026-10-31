-- Extend existing immutable evidence observations; no key provisioning or legal approval.
-- Compensation: revoke reviewed contract key scopes / disable acquisition activation;
-- preserve observations, artifacts and audits. Never delete evidence to roll back.
BEGIN;
CREATE TABLE private.acquisition_contract_verification_key_scopes (
 workspace_id uuid NOT NULL, key_id uuid NOT NULL,
 purpose text NOT NULL CHECK(purpose IN ('purchase_contract','title_report','assignment_agreement','seller_disclosure','assignee_disclosure','closing_statement','supporting_document')),
 reviewed_by uuid NOT NULL REFERENCES public.profiles(id), approval_ref uuid NOT NULL,
 valid_from timestamptz NOT NULL CHECK(isfinite(valid_from)), valid_until timestamptz NOT NULL CHECK(isfinite(valid_until)),
 revoked_at timestamptz CHECK(isfinite(revoked_at)),
 PRIMARY KEY(workspace_id,key_id,purpose),
 FOREIGN KEY(workspace_id,key_id) REFERENCES private.acquisition_evidence_verification_keys(workspace_id,id),
 CHECK(valid_from<valid_until AND valid_until-valid_from<=interval '24 hours')
);
ALTER TABLE private.acquisition_contract_verification_key_scopes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_contract_verification_key_scopes FROM PUBLIC,anon,authenticated,service_role;
-- Intentionally empty. Existing reviewed mail keys gain no contract-purpose authority.
ALTER TABLE public.acquisition_evidence_artifacts ADD CONSTRAINT acquisition_contract_artifact_purpose
 UNIQUE(workspace_id,contract_id,contract_version,id,purpose);
ALTER TABLE public.acquisition_evidence_verifications ALTER COLUMN campaign_id DROP NOT NULL,
 ADD COLUMN contract_id uuid, ADD COLUMN contract_version integer, ADD COLUMN contract_purpose text,
 ADD CONSTRAINT acquisition_verification_target CHECK(
  (campaign_id IS NOT NULL AND contract_id IS NULL AND contract_version IS NULL AND contract_purpose IS NULL) OR
  (campaign_id IS NULL AND contract_id IS NOT NULL AND contract_version IS NOT NULL AND contract_version>0 AND contract_purpose IS NOT NULL)),
 ADD CONSTRAINT acquisition_verification_contract FOREIGN KEY(workspace_id,contract_id,contract_version,artifact_id,contract_purpose)
  REFERENCES public.acquisition_evidence_artifacts(workspace_id,contract_id,contract_version,id,purpose),
 ADD CONSTRAINT acquisition_verification_contract_scope FOREIGN KEY(workspace_id,key_id,contract_purpose)
  REFERENCES private.acquisition_contract_verification_key_scopes(workspace_id,key_id,purpose),
 ADD CONSTRAINT acquisition_verification_contract_identity UNIQUE(workspace_id,contract_id,contract_version,artifact_id,id);
CREATE INDEX acquisition_contract_verification_history ON public.acquisition_evidence_verifications(workspace_id,contract_id,contract_version,artifact_id,created_at,id) WHERE contract_id IS NOT NULL;
-- Existing workspace/actor RLS, immutable trigger, raw-write denial and detected-byte
-- index remain in force. Shared hash locks and detection queries cover both targets.
CREATE FUNCTION private.record_contract_document_verification(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_purpose text,p_artifact uuid,
 p_actor uuid,p_session uuid,p_key uuid,p_observation text,p_signature text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE artifact public.acquisition_evidence_artifacts%ROWTYPE; signer private.acquisition_evidence_verification_keys%ROWTYPE;
 saved public.acquisition_evidence_verifications%ROWTYPE; policy private.acquisition_evidence_policies%ROWTYPE;
 payload jsonb; raw json; field text; message text; fingerprint text; expected bytea; supplied bytea; difference integer:=0;
 actor_updated timestamptz; session_expires timestamptz; stamped timestamptz; checked timestamptz; scanned timestamptz;
 registry_checked timestamptz; retained timestamptz; role_name text; authority record; scope private.acquisition_contract_verification_key_scopes%ROWTYPE;
BEGIN
 role_name:=private.acquisition_role(p_workspace);
 IF auth.jwt()->>'role' IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(role_name,'') NOT IN ('owner','admin','operator') OR p_actor IS DISTINCT FROM auth.uid()
  OR p_session::text IS DISTINCT FROM auth.jwt()->>'session_id' THEN
  RAISE EXCEPTION 'Verification authority required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_contract IS NULL OR p_version IS NULL OR p_version<1
  OR p_purpose IS NULL OR p_purpose NOT IN ('purchase_contract','title_report','assignment_agreement','seller_disclosure','assignee_disclosure','closing_statement','supporting_document') OR p_artifact IS NULL OR p_actor IS NULL OR p_session IS NULL OR p_key IS NULL
  OR p_observation IS NULL OR octet_length(p_observation) NOT BETWEEN 2 AND 4096
  OR p_signature IS NULL OR p_signature !~ '^[0-9a-f]{64}$' THEN
  RAISE EXCEPTION 'Bounded signed observation required' USING ERRCODE='22023'; END IF;
 raw:=p_observation::json; payload:=raw::jsonb;
 IF jsonb_typeof(payload) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'Object observation required' USING ERRCODE='22023'; END IF;
 IF (SELECT count(*) FROM json_each(raw))<>12 OR (SELECT count(DISTINCT key) FROM json_each(raw))<>12
  OR payload - ARRAY['sha256','byte_size','media_type','retain_until','retention_policy_id','checked_at','scan_checked_at',
                    'registry_checked_at','scanner','scanner_version','scan_policy_version','scan_status'] <> '{}'::jsonb THEN
  RAISE EXCEPTION 'Exact observation fields required' USING ERRCODE='22023'; END IF;
 FOR field IN SELECT jsonb_object_keys(payload) LOOP
  IF field='byte_size' THEN
   IF jsonb_typeof(payload->field)<>'number' OR (payload->>field) !~ '^[1-9][0-9]{0,7}$' THEN
    RAISE EXCEPTION 'Integer evidence size required' USING ERRCODE='22023'; END IF;
  ELSIF jsonb_typeof(payload->field) IS DISTINCT FROM 'string' THEN
   RAISE EXCEPTION 'String observation field required' USING ERRCODE='22023'; END IF;
 END LOOP;
 IF payload->>'sha256' !~ '^[0-9a-f]{64}$' OR (payload->>'byte_size')::integer NOT BETWEEN 1 AND 10485760
  OR payload->>'scanner'<>'clamav-instream-v1' OR payload->>'scan_status' NOT IN ('no_detection','detected') THEN
  RAISE EXCEPTION 'Valid scan observation required' USING ERRCODE='22023'; END IF;
 FOREACH field IN ARRAY ARRAY['checked_at','scan_checked_at','registry_checked_at','retain_until'] LOOP
  IF payload->>field !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
   RAISE EXCEPTION 'Explicit observation timestamp required' USING ERRCODE='22023'; END IF;
 END LOOP;
 checked:=(payload->>'checked_at')::timestamptz; scanned:=(payload->>'scan_checked_at')::timestamptz;
 registry_checked:=(payload->>'registry_checked_at')::timestamptz; retained:=(payload->>'retain_until')::timestamptz;
 message:='acquisition-contract-document-attestation-v1'||chr(10)||p_id::text||chr(10)||p_workspace::text||chr(10)||p_contract::text||chr(10)||p_version::text||chr(10)||p_purpose||chr(10)||
  p_artifact::text||chr(10)||p_actor::text||chr(10)||p_session::text||chr(10)||p_key::text||chr(10)||p_observation;
 fingerprint:=encode(sha256(convert_to(message||chr(10)||p_signature,'UTF8')),'hex');
 SELECT * INTO authority FROM private.lock_contract_document_context(p_workspace,p_contract,p_version,ARRAY['owner','admin','operator']);
 actor_updated:=authority.actor_updated; session_expires:=authority.session_expires;
 role_name:=private.acquisition_role(p_workspace);
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-verification:'||p_id::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||p_artifact::text,0));
 IF session_expires IS NOT NULL AND session_expires<=clock_timestamp() THEN RAISE EXCEPTION 'Verification session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_evidence_verifications WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Verification request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('verification_id',saved.id,'artifact_id',saved.artifact_id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,'purpose',saved.contract_purpose,
   'scan_status',saved.scan_status,'duplicate',true,'observation_persisted',true,'preview_authorized',false,'legal_review_approved',false,'execution_authorized',false);
 END IF;
 SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND contract_id=p_contract AND contract_version=p_version AND purpose=p_purpose AND campaign_id IS NULL AND id=p_artifact;
 IF NOT FOUND OR (role_name='operator' AND artifact.created_by<>auth.uid()) THEN RAISE EXCEPTION 'Artifact unavailable' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||artifact.expected_sha256,0));
 SELECT * INTO signer FROM private.acquisition_evidence_verification_keys WHERE id=p_key AND workspace_id=p_workspace FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Verification signer unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO scope FROM private.acquisition_contract_verification_key_scopes WHERE workspace_id=p_workspace AND key_id=p_key AND purpose=p_purpose FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Reviewed contract signing scope required' USING ERRCODE='42501'; END IF;
 SELECT * INTO policy FROM private.acquisition_evidence_policies WHERE id=artifact.retention_policy_id AND workspace_id=p_workspace AND purpose=p_purpose FOR SHARE;
 stamped:=clock_timestamp();
 IF session_expires IS NOT NULL AND session_expires<=stamped THEN RAISE EXCEPTION 'Verification session expired' USING ERRCODE='42501'; END IF;
 IF scope.revoked_at IS NOT NULL OR NOT(scope.valid_from<=checked AND scope.valid_from<=stamped AND stamped<scope.valid_until)
  OR signer.revoked_at IS NOT NULL OR NOT(signer.valid_from<=checked AND signer.valid_from<=stamped AND stamped<signer.valid_until)
  OR signer.scanner_version IS DISTINCT FROM payload->>'scanner_version'
  OR signer.scan_policy_version IS DISTINCT FROM payload->>'scan_policy_version' THEN
  RAISE EXCEPTION 'Current reviewed scanner required' USING ERRCODE='42501'; END IF;
 expected:=extensions.hmac(convert_to(message,'UTF8'),signer.secret,'sha256'); supplied:=decode(p_signature,'hex');
 FOR n IN 0..31 LOOP difference:=difference | (get_byte(expected,n) # get_byte(supplied,n)); END LOOP;
 IF difference<>0 THEN RAISE EXCEPTION 'Invalid verification signature' USING ERRCODE='42501'; END IF;
 IF NOT isfinite(checked) OR NOT isfinite(scanned) OR NOT isfinite(registry_checked) OR NOT isfinite(retained)
  OR checked<artifact.created_at-interval '5 seconds' OR checked<stamped-interval '120 seconds' OR checked>scanned OR scanned>stamped+interval '5 seconds'
  OR registry_checked<scanned-interval '5 seconds' OR registry_checked>stamped+interval '5 seconds'
  OR retained<=greatest(checked,scanned,registry_checked)
  OR artifact.retain_until<=stamped OR retained IS DISTINCT FROM artifact.retain_until
  OR (payload->>'retention_policy_id')::uuid IS DISTINCT FROM artifact.retention_policy_id
  OR payload->>'sha256' IS DISTINCT FROM artifact.expected_sha256 OR (payload->>'byte_size')::integer<>artifact.expected_byte_size
  OR payload->>'media_type' IS DISTINCT FROM artifact.media_type OR policy.id IS NULL OR policy.revoked_at IS NOT NULL
  OR NOT(policy.valid_from<=stamped AND stamped<policy.valid_until)
  OR EXISTS(SELECT 1 FROM public.acquisition_evidence_revocations WHERE artifact_id=p_artifact) THEN
  RAISE EXCEPTION 'Evidence changed or observation expired' USING ERRCODE='55000'; END IF;
 INSERT INTO public.acquisition_evidence_verifications(id,workspace_id,contract_id,contract_version,contract_purpose,artifact_id,actor_id,session_id,
  actor_membership_updated_at,key_id,scan_status,observation,request_hash,created_at)
 VALUES(p_id,p_workspace,p_contract,p_version,p_purpose,p_artifact,p_actor,p_session,actor_updated,p_key,payload->>'scan_status',payload,fingerprint,stamped)
 RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_evidence_verification',p_id::text,'recorded',auth.uid()::text,p_workspace,
  jsonb_build_object('artifact_id',p_artifact,'contract_id',p_contract,'contract_version',p_version,'purpose',p_purpose,'scan_status',saved.scan_status,'key_id',p_key,
                    'preview_authorized',false,'legal_review_approved',false,'execution_authorized',false));
 RETURN jsonb_build_object('verification_id',saved.id,'artifact_id',saved.artifact_id,'workspace_id',saved.workspace_id,'contract_id',saved.contract_id,'contract_version',saved.contract_version,'purpose',saved.contract_purpose,
  'scan_status',saved.scan_status,'duplicate',false,'observation_persisted',true,'preview_authorized',false,'legal_review_approved',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.record_contract_document_verification(p_id uuid,p_workspace uuid,p_contract uuid,p_version integer,p_purpose text,p_artifact uuid,
 p_actor uuid,p_session uuid,p_key uuid,p_observation text,p_signature text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.record_contract_document_verification(p_id,p_workspace,p_contract,p_version,p_purpose,p_artifact,p_actor,p_session,p_key,p_observation,p_signature)
$$;
REVOKE ALL ON FUNCTION private.record_contract_document_verification(uuid,uuid,uuid,integer,text,uuid,uuid,uuid,uuid,text,text) FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.record_contract_document_verification(uuid,uuid,uuid,integer,text,uuid,uuid,uuid,uuid,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_contract_document_verification(uuid,uuid,uuid,integer,text,uuid,uuid,uuid,uuid,text,text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.record_contract_document_verification(uuid,uuid,uuid,integer,text,uuid,uuid,uuid,uuid,text,text) TO authenticated;
COMMIT;
