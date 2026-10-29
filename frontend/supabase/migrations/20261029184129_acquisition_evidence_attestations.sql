-- Local proposal only. Signed scan observations are not preview or approval authority.
BEGIN;
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;
DO $$ BEGIN
 IF (SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='pgcrypto') IS DISTINCT FROM 'extensions' THEN
  RAISE EXCEPTION 'Reviewed pgcrypto installation in extensions required'; END IF;
END $$;
CREATE TABLE private.acquisition_evidence_verification_keys (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES public.workspaces(id),
 secret bytea NOT NULL CHECK(octet_length(secret)=32),
 scanner_version text NOT NULL CHECK(length(scanner_version)<=160 AND scanner_version ~ '^ClamAV [0-9]+\.[0-9]+\.[0-9]+/[0-9]+/[ -~]{1,100}$'),
 scan_policy_version text NOT NULL CHECK(scan_policy_version ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'),
 valid_from timestamptz NOT NULL CHECK(isfinite(valid_from)), valid_until timestamptz NOT NULL CHECK(isfinite(valid_until)),
 reviewed_by uuid NOT NULL REFERENCES public.profiles(id), approval_ref uuid NOT NULL,
 revoked_at timestamptz CHECK(isfinite(revoked_at)),
 UNIQUE(workspace_id,id), CHECK(valid_from<valid_until AND valid_until-valid_from<=interval '24 hours')
);
ALTER TABLE private.acquisition_evidence_verification_keys ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_evidence_verification_keys FROM PUBLIC,anon,authenticated,service_role;
-- Intentionally empty. Neither application users nor this migration provision signing secrets.
CREATE TABLE public.acquisition_evidence_verifications (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, campaign_id uuid NOT NULL, artifact_id uuid NOT NULL,
 actor_id uuid NOT NULL REFERENCES public.profiles(id), session_id uuid NOT NULL,
 actor_membership_updated_at timestamptz NOT NULL, key_id uuid NOT NULL,
 scan_status text NOT NULL CHECK(scan_status IN ('no_detection','detected')),
 observation jsonb NOT NULL CHECK(jsonb_typeof(observation)='object'),
 request_hash text NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,id),
 FOREIGN KEY(workspace_id,campaign_id,artifact_id) REFERENCES public.acquisition_evidence_artifacts(workspace_id,campaign_id,id),
 FOREIGN KEY(workspace_id,key_id) REFERENCES private.acquisition_evidence_verification_keys(workspace_id,id)
);
CREATE INDEX acquisition_evidence_verification_history ON public.acquisition_evidence_verifications(workspace_id,artifact_id,created_at,id);
ALTER TABLE public.acquisition_evidence_verifications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_evidence_verifications FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_evidence_verifications TO authenticated;
CREATE POLICY acquisition_evidence_verification_read ON public.acquisition_evidence_verifications FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin') OR
       (private.acquisition_role(workspace_id)='operator' AND actor_id=auth.uid()));
CREATE TRIGGER acquisition_evidence_verification_immutable BEFORE UPDATE OR DELETE ON public.acquisition_evidence_verifications
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

CREATE FUNCTION private.record_acquisition_evidence_verification(p_id uuid,p_workspace uuid,p_campaign uuid,p_artifact uuid,
 p_actor uuid,p_session uuid,p_key uuid,p_observation text,p_signature text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE artifact public.acquisition_evidence_artifacts%ROWTYPE; signer private.acquisition_evidence_verification_keys%ROWTYPE;
 saved public.acquisition_evidence_verifications%ROWTYPE; policy private.acquisition_evidence_policies%ROWTYPE;
 payload jsonb; raw json; field text; message text; fingerprint text; expected bytea; supplied bytea; difference integer:=0;
 actor_updated timestamptz; session_expires timestamptz; stamped timestamptz; checked timestamptz; scanned timestamptz;
 registry_checked timestamptz; retained timestamptz; role_name text;
BEGIN
 role_name:=private.acquisition_role(p_workspace);
 IF auth.jwt()->>'role' IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
  OR coalesce(role_name,'') NOT IN ('owner','admin','operator') OR p_actor IS DISTINCT FROM auth.uid()
  OR p_session::text IS DISTINCT FROM auth.jwt()->>'session_id' THEN
  RAISE EXCEPTION 'Verification authority required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_campaign IS NULL OR p_artifact IS NULL OR p_actor IS NULL OR p_session IS NULL OR p_key IS NULL
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
 message:='acquisition-evidence-attestation-v1'||chr(10)||p_id::text||chr(10)||p_workspace::text||chr(10)||p_campaign::text||chr(10)||
  p_artifact::text||chr(10)||p_actor::text||chr(10)||p_session::text||chr(10)||p_key::text||chr(10)||p_observation;
 fingerprint:=encode(sha256(convert_to(message||chr(10)||p_signature,'UTF8')),'hex');
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 SELECT m.role,m.updated_at,s.not_after INTO role_name,actor_updated,session_expires FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
 JOIN auth.sessions s ON s.user_id=p.id WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active'
  AND m.role IN ('owner','admin','operator') AND p.status='approved' AND s.id=p_session
  AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Verification session unavailable' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-verification:'||p_id::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||p_artifact::text,0));
 IF session_expires IS NOT NULL AND session_expires<=clock_timestamp() THEN RAISE EXCEPTION 'Verification session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_evidence_verifications WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Verification request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('verification_id',saved.id,'artifact_id',saved.artifact_id,'workspace_id',saved.workspace_id,
   'scan_status',saved.scan_status,'duplicate',true,'observation_persisted',true,'preview_authorized',false,'content_approved',false,'execution_authorized',false);
 END IF;
 SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND campaign_id=p_campaign AND id=p_artifact;
 IF NOT FOUND OR (role_name='operator' AND artifact.created_by<>auth.uid()) THEN RAISE EXCEPTION 'Artifact unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.ad_campaigns WHERE id=p_campaign AND workspace_id=p_workspace AND acquisition_channel='direct_mail' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Campaign unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO signer FROM private.acquisition_evidence_verification_keys WHERE id=p_key AND workspace_id=p_workspace FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Verification signer unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO policy FROM private.acquisition_evidence_policies WHERE id=artifact.retention_policy_id FOR SHARE;
 stamped:=clock_timestamp();
 IF session_expires IS NOT NULL AND session_expires<=stamped THEN RAISE EXCEPTION 'Verification session expired' USING ERRCODE='42501'; END IF;
 IF signer.revoked_at IS NOT NULL OR NOT(signer.valid_from<=checked AND signer.valid_from<=stamped AND stamped<signer.valid_until)
  OR signer.scanner_version IS DISTINCT FROM payload->>'scanner_version'
  OR signer.scan_policy_version IS DISTINCT FROM payload->>'scan_policy_version' THEN
  RAISE EXCEPTION 'Current reviewed scanner required' USING ERRCODE='42501'; END IF;
 expected:=extensions.hmac(convert_to(message,'UTF8'),signer.secret,'sha256'); supplied:=decode(p_signature,'hex');
 FOR n IN 0..31 LOOP difference:=difference | (get_byte(expected,n) # get_byte(supplied,n)); END LOOP;
 IF difference<>0 THEN RAISE EXCEPTION 'Invalid verification signature' USING ERRCODE='42501'; END IF;
 IF NOT isfinite(checked) OR NOT isfinite(scanned) OR NOT isfinite(registry_checked) OR NOT isfinite(retained)
  OR checked<artifact.created_at-interval '5 seconds' OR checked<stamped-interval '120 seconds' OR checked>scanned OR scanned>stamped+interval '5 seconds'
  OR registry_checked<scanned-interval '5 seconds' OR registry_checked>stamped+interval '5 seconds'
  OR artifact.retain_until<=stamped OR retained IS DISTINCT FROM artifact.retain_until
  OR (payload->>'retention_policy_id')::uuid IS DISTINCT FROM artifact.retention_policy_id
  OR payload->>'sha256' IS DISTINCT FROM artifact.expected_sha256 OR (payload->>'byte_size')::integer<>artifact.expected_byte_size
  OR payload->>'media_type' IS DISTINCT FROM artifact.media_type OR policy.revoked_at IS NOT NULL
  OR NOT(policy.valid_from<=stamped AND stamped<policy.valid_until)
  OR EXISTS(SELECT 1 FROM public.acquisition_evidence_revocations WHERE artifact_id=p_artifact) THEN
  RAISE EXCEPTION 'Evidence changed or observation expired' USING ERRCODE='55000'; END IF;
 INSERT INTO public.acquisition_evidence_verifications(id,workspace_id,campaign_id,artifact_id,actor_id,session_id,
  actor_membership_updated_at,key_id,scan_status,observation,request_hash,created_at)
 VALUES(p_id,p_workspace,p_campaign,p_artifact,p_actor,p_session,actor_updated,p_key,payload->>'scan_status',payload,fingerprint,stamped)
 RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_evidence_verification',p_id::text,'recorded',auth.uid()::text,p_workspace,
  jsonb_build_object('artifact_id',p_artifact,'campaign_id',p_campaign,'scan_status',saved.scan_status,'key_id',p_key,
                    'preview_authorized',false,'content_approved',false,'execution_authorized',false));
 RETURN jsonb_build_object('verification_id',saved.id,'artifact_id',saved.artifact_id,'workspace_id',saved.workspace_id,
  'scan_status',saved.scan_status,'duplicate',false,'observation_persisted',true,'preview_authorized',false,'content_approved',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.record_acquisition_evidence_verification(p_id uuid,p_workspace uuid,p_campaign uuid,p_artifact uuid,
 p_actor uuid,p_session uuid,p_key uuid,p_observation text,p_signature text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.record_acquisition_evidence_verification(p_id,p_workspace,p_campaign,p_artifact,p_actor,p_session,p_key,p_observation,p_signature)
$$;
REVOKE ALL ON FUNCTION private.record_acquisition_evidence_verification(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text) FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.record_acquisition_evidence_verification(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_acquisition_evidence_verification(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.record_acquisition_evidence_verification(uuid,uuid,uuid,uuid,uuid,uuid,uuid,text,text) TO authenticated;
COMMIT;
