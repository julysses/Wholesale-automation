-- Forward-only: historical attestations remain intact but do not become verified bindings.
BEGIN;
ALTER TABLE public.acquisition_mail_content_reviews ADD CONSTRAINT acquisition_content_review_campaign_id UNIQUE(workspace_id,campaign_id,id);
ALTER TABLE public.acquisition_evidence_verifications ADD CONSTRAINT acquisition_verification_artifact_id UNIQUE(workspace_id,campaign_id,artifact_id,id);
CREATE TABLE private.acquisition_content_evidence_bindings (
 review_id uuid PRIMARY KEY, workspace_id uuid NOT NULL, campaign_id uuid NOT NULL,
 artifact_id uuid NOT NULL, verification_id uuid NOT NULL,
 sha256 text NOT NULL CHECK(sha256 ~ '^[0-9a-f]{64}$'), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,campaign_id,review_id) REFERENCES public.acquisition_mail_content_reviews(workspace_id,campaign_id,id),
 FOREIGN KEY(workspace_id,campaign_id,artifact_id) REFERENCES public.acquisition_evidence_artifacts(workspace_id,campaign_id,id),
 FOREIGN KEY(workspace_id,campaign_id,artifact_id,verification_id) REFERENCES public.acquisition_evidence_verifications(workspace_id,campaign_id,artifact_id,id)
);
ALTER TABLE private.acquisition_content_evidence_bindings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_content_evidence_bindings FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_content_binding_immutable BEFORE UPDATE OR DELETE ON private.acquisition_content_evidence_bindings
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();
CREATE FUNCTION private.acquisition_content_evidence_current(p_workspace uuid,p_campaign uuid,p_artifact uuid,p_hash text,p_verification uuid,p_at timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path='' AS $$
 SELECT EXISTS(
  SELECT 1 FROM public.acquisition_evidence_artifacts a
  JOIN public.acquisition_evidence_verifications v ON v.workspace_id=a.workspace_id AND v.campaign_id=a.campaign_id AND v.artifact_id=a.id AND v.id=p_verification
  JOIN private.acquisition_evidence_policies policy ON policy.workspace_id=a.workspace_id AND policy.id=a.retention_policy_id
  JOIN private.acquisition_evidence_verification_keys k ON k.workspace_id=v.workspace_id AND k.id=v.key_id
  JOIN public.workspace_memberships m ON m.workspace_id=v.workspace_id AND m.user_id=v.actor_id
  JOIN public.profiles profile ON profile.id=m.user_id
  JOIN auth.sessions session ON session.id=v.session_id AND session.user_id=v.actor_id
  WHERE a.workspace_id=p_workspace AND a.campaign_id=p_campaign AND a.id=p_artifact AND a.expected_sha256=p_hash
   AND a.purpose='mail_content' AND a.created_at<=p_at AND a.retain_until>p_at
   AND policy.purpose=a.purpose AND policy.revoked_at IS NULL AND policy.valid_from<=p_at AND p_at<policy.valid_until
   AND v.scan_status='no_detection' AND v.created_at<=p_at
   AND v.id=(SELECT id FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND artifact_id=p_artifact ORDER BY created_at DESC,id DESC LIMIT 1)
   AND k.revoked_at IS NULL AND k.valid_from<=p_at AND p_at<k.valid_until
   AND k.valid_from<=(v.observation->>'checked_at')::timestamptz
   AND k.scanner_version=v.observation->>'scanner_version' AND k.scan_policy_version=v.observation->>'scan_policy_version'
   AND m.status='active' AND m.role IN ('owner','admin','operator') AND m.updated_at=v.actor_membership_updated_at
   AND profile.status='approved' AND (session.not_after IS NULL OR session.not_after>p_at)
   AND NOT EXISTS(SELECT 1 FROM public.acquisition_evidence_revocations WHERE workspace_id=p_workspace AND artifact_id=p_artifact)
   AND NOT EXISTS(SELECT 1 FROM public.acquisition_evidence_verifications WHERE workspace_id=p_workspace AND scan_status='detected' AND observation->>'sha256'=p_hash)
 )
$$;
REVOKE ALL ON FUNCTION private.acquisition_content_evidence_current(uuid,uuid,uuid,text,uuid,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION private.lock_acquisition_content_evidence(p_workspace uuid,p_campaign uuid,p_artifact uuid,p_hash text,p_expires timestamptz)
RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE artifact public.acquisition_evidence_artifacts%ROWTYPE; observation public.acquisition_evidence_verifications%ROWTYPE;
 deadline timestamptz; checked timestamptz;
BEGIN
 -- Invoked only by the owner/admin review transaction. Never exposed as an RPC.
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||p_artifact::text,0));
 SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND campaign_id=p_campaign AND id=p_artifact;
 IF NOT FOUND OR artifact.expected_sha256 IS DISTINCT FROM p_hash OR artifact.purpose<>'mail_content' THEN
  RAISE EXCEPTION 'Registered content evidence required' USING ERRCODE='55000'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||artifact.expected_sha256,0));
 SELECT * INTO observation FROM public.acquisition_evidence_verifications
  WHERE workspace_id=p_workspace AND campaign_id=p_campaign AND artifact_id=p_artifact ORDER BY created_at DESC,id DESC LIMIT 1;
 IF NOT FOUND THEN RAISE EXCEPTION 'Verified content evidence required' USING ERRCODE='55000'; END IF;
 SELECT least(artifact.retain_until,policy.valid_until,k.valid_until,session.not_after) INTO deadline
  FROM private.acquisition_evidence_verification_keys k
  JOIN private.acquisition_evidence_policies policy ON policy.id=artifact.retention_policy_id AND policy.workspace_id=p_workspace
  JOIN public.workspace_memberships m ON m.workspace_id=p_workspace AND m.user_id=observation.actor_id
  JOIN public.profiles profile ON profile.id=m.user_id
  JOIN auth.sessions session ON session.id=observation.session_id AND session.user_id=m.user_id
  WHERE k.id=observation.key_id AND k.workspace_id=p_workspace FOR SHARE OF k,policy,m,profile,session;
 checked:=clock_timestamp();
 IF deadline IS NULL OR p_expires IS NULL OR NOT isfinite(p_expires) OR p_expires<=checked OR p_expires>deadline
  OR NOT private.acquisition_content_evidence_current(p_workspace,p_campaign,p_artifact,p_hash,observation.id,checked) THEN
  RAISE EXCEPTION 'Current retained scan evidence required' USING ERRCODE='55000'; END IF;
 RETURN observation.id;
END $$;
REVOKE ALL ON FUNCTION private.lock_acquisition_content_evidence(uuid,uuid,uuid,text,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
CREATE OR REPLACE FUNCTION private.record_acquisition_evidence_verification(p_id uuid,p_workspace uuid,p_campaign uuid,p_artifact uuid,
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
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-bytes:'||p_workspace::text||':'||artifact.expected_sha256,0));
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
CREATE OR REPLACE FUNCTION private.review_acquisition_mail_content(p_id uuid,p_workspace uuid,p_campaign uuid,p_content uuid,
 p_expected_version integer,p_action text,p_creative uuid,p_destination_review uuid,p_company_name text,
 p_preparation_hash text,p_evidence_ref uuid,p_evidence_hash text,p_expires_at timestamptz,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_mail_content_reviews%ROWTYPE; latest public.acquisition_mail_content_reviews%ROWTYPE;
 active boolean; actor_updated timestamptz; request_hash text; prepared jsonb; renderer text;
 template_id uuid; destination_id uuid; destination_actor uuid; session_expires timestamptz; bound_verification uuid;
BEGIN
 IF auth.jwt()->>'aal' IS DISTINCT FROM 'aal2' OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') THEN
  RAISE EXCEPTION 'Content reviewer with MFA required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_campaign IS NULL OR p_content IS NULL OR p_expected_version IS NULL
  OR p_expected_version NOT BETWEEN 0 AND 999999999 OR p_action IS NULL OR p_action NOT IN ('approved','withdrawn')
  OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 20 AND 2000 THEN
  RAISE EXCEPTION 'Documented content review required' USING ERRCODE='22023'; END IF;
 IF p_action='withdrawn' AND (p_creative IS NOT NULL OR p_destination_review IS NOT NULL OR p_company_name IS NOT NULL
  OR p_preparation_hash IS NOT NULL OR p_evidence_ref IS NOT NULL OR p_evidence_hash IS NOT NULL OR p_expires_at IS NOT NULL) THEN
  RAISE EXCEPTION 'Withdrawal must retain prior content evidence' USING ERRCODE='22023'; END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF p_action='approved' AND active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 SELECT m.updated_at,s.not_after INTO actor_updated,session_expires FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
 JOIN auth.sessions s ON s.user_id=p.id WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active'
  AND m.role IN ('owner','admin') AND p.status='approved' AND s.id::text=auth.jwt()->>'session_id'
  AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Content review authority changed' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.ad_campaigns WHERE id=p_campaign AND workspace_id=p_workspace AND acquisition_channel='direct_mail'
  AND (p_action='withdrawn' OR status='draft') FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Mail campaign unavailable' USING ERRCODE='42501'; END IF;
 request_hash:=encode(sha256(convert_to(jsonb_build_array(p_workspace,p_campaign,p_content,p_expected_version,p_action,
  p_creative,p_destination_review,p_company_name,p_preparation_hash,p_evidence_ref,p_evidence_hash,
  extract(epoch from p_expires_at),p_note,auth.uid())::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended('mail-content-request:'||p_id::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('mail-content:'||p_workspace::text||':'||p_content::text,0));
 IF session_expires IS NOT NULL AND session_expires<=clock_timestamp() THEN
  RAISE EXCEPTION 'Content review session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_mail_content_reviews WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM request_hash THEN RAISE EXCEPTION 'Content request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'content_id',saved.content_id,
   'version',saved.version,'duplicate',true,'execution_authorized',false);
 END IF;
 SELECT * INTO latest FROM public.acquisition_mail_content_reviews WHERE workspace_id=p_workspace AND content_id=p_content ORDER BY version DESC LIMIT 1;
 IF coalesce(latest.version,0)<>p_expected_version OR (latest.id IS NOT NULL AND latest.campaign_id<>p_campaign) THEN
  RAISE EXCEPTION 'Content review changed' USING ERRCODE='40001'; END IF;
 IF p_action='withdrawn' THEN
  IF latest.id IS NULL OR latest.action='withdrawn' THEN RAISE EXCEPTION 'Existing content approval required' USING ERRCODE='55000'; END IF;
  p_creative:=latest.creative_id;p_destination_review:=latest.destination_review_id;p_company_name:=latest.company_name;
  p_preparation_hash:=latest.preparation_hash;p_evidence_ref:=latest.evidence_ref;p_evidence_hash:=latest.evidence_hash;
  p_expires_at:=latest.expires_at;renderer:=latest.renderer_version;
 ELSE
  IF p_creative IS NULL OR p_destination_review IS NULL OR p_preparation_hash IS NULL OR p_preparation_hash !~ '^[0-9a-f]{64}$'
   OR p_evidence_ref IS NULL OR p_evidence_hash IS NULL OR p_evidence_hash !~ '^[0-9a-f]{64}$'
   OR p_expires_at IS NULL OR NOT isfinite(p_expires_at) OR p_expires_at<=clock_timestamp() THEN
   RAISE EXCEPTION 'Current content review evidence required' USING ERRCODE='22023'; END IF;
  SELECT acquisition_template_id INTO template_id FROM public.ad_creatives
   WHERE id=p_creative AND workspace_id=p_workspace AND campaign_id=p_campaign;
  IF NOT FOUND OR template_id IS NULL THEN RAISE EXCEPTION 'Mail template unavailable' USING ERRCODE='42501'; END IF;
  SELECT d.destination_id,d.actor_id INTO destination_id,destination_actor FROM public.acquisition_mail_destination_reviews d
   WHERE d.id=p_destination_review AND d.workspace_id=p_workspace AND d.campaign_id=p_campaign;
  IF NOT FOUND THEN RAISE EXCEPTION 'Mail destination unavailable' USING ERRCODE='42501'; END IF;
  -- Same source locks as template/destination writers. Recompute after waiting for them.
  PERFORM pg_advisory_xact_lock(hashtextextended('mail-template:'||p_workspace::text||':'||template_id::text,0));
  PERFORM pg_advisory_xact_lock(hashtextextended('mail-destination:'||p_workspace::text||':'||destination_id::text,0));
  PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
   WHERE m.workspace_id=p_workspace AND m.user_id=destination_actor FOR SHARE OF m,p;
  prepared:=private.prepare_acquisition_mail_content(p_workspace,p_campaign,p_creative,p_destination_review,p_company_name);
  IF prepared->>'preparation_hash' IS DISTINCT FROM p_preparation_hash THEN
   RAISE EXCEPTION 'Prepared content changed; review again' USING ERRCODE='40001'; END IF;
  IF p_expires_at>(prepared->>'destination_valid_until')::timestamptz OR p_expires_at<=clock_timestamp()
   OR (prepared->>'destination_valid_until')::timestamptz<=clock_timestamp() THEN
   RAISE EXCEPTION 'Content review expiry must fit current destination evidence' USING ERRCODE='22023'; END IF;
  renderer:=prepared->'snapshot'->>'renderer_version';
  bound_verification:=private.lock_acquisition_content_evidence(p_workspace,p_campaign,p_evidence_ref,p_evidence_hash,p_expires_at);
 END IF;
 IF session_expires IS NOT NULL AND session_expires<=clock_timestamp() THEN
  RAISE EXCEPTION 'Content review session expired' USING ERRCODE='42501'; END IF;
 IF p_action='approved' AND p_expires_at<=clock_timestamp() THEN
  RAISE EXCEPTION 'Content review evidence expired' USING ERRCODE='55000'; END IF;
 INSERT INTO public.acquisition_mail_content_reviews(id,workspace_id,campaign_id,content_id,version,action,
  creative_id,destination_review_id,company_name,renderer_version,preparation_hash,evidence_ref,evidence_hash,expires_at,
  review_note,actor_id,actor_membership_updated_at,request_hash)
 VALUES(p_id,p_workspace,p_campaign,p_content,p_expected_version+1,p_action,p_creative,p_destination_review,p_company_name,
  renderer,p_preparation_hash,p_evidence_ref,p_evidence_hash,p_expires_at,p_note,auth.uid(),actor_updated,request_hash) RETURNING * INTO saved;
 IF p_action='approved' THEN
  INSERT INTO private.acquisition_content_evidence_bindings(review_id,workspace_id,campaign_id,artifact_id,verification_id,sha256)
  VALUES(p_id,p_workspace,p_campaign,p_evidence_ref,bound_verification,p_evidence_hash);
 END IF;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_mail_content',p_content::text,p_action,auth.uid()::text,p_workspace,
  jsonb_build_object('review_id',p_id,'version',saved.version,'campaign_id',p_campaign,'creative_id',p_creative,
   'destination_review_id',p_destination_review,'evidence_verification_id',bound_verification,'execution_authorized',false));
 RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'content_id',saved.content_id,
  'version',saved.version,'duplicate',false,'execution_authorized',false);
END $$;
CREATE OR REPLACE FUNCTION private.acquisition_mail_content_state(p_workspace uuid,p_campaign uuid,p_content uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE latest public.acquisition_mail_content_reviews%ROWTYPE; valid boolean:=false; prepared jsonb:=NULL;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Content review access denied' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.ad_campaigns WHERE id=p_campaign AND workspace_id=p_workspace AND acquisition_channel='direct_mail';
 IF NOT FOUND THEN RAISE EXCEPTION 'Mail campaign unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO latest FROM public.acquisition_mail_content_reviews WHERE workspace_id=p_workspace AND campaign_id=p_campaign
  AND content_id=p_content ORDER BY version DESC LIMIT 1;
 IF latest.id IS NOT NULL AND latest.action='approved' AND latest.expires_at>statement_timestamp()
  AND latest.created_at<=statement_timestamp()
  AND EXISTS(SELECT 1 FROM private.acquisition_content_evidence_bindings b WHERE b.review_id=latest.id
   AND b.workspace_id=p_workspace AND b.campaign_id=p_campaign AND b.artifact_id=latest.evidence_ref AND b.sha256=latest.evidence_hash
   AND private.acquisition_content_evidence_current(p_workspace,p_campaign,b.artifact_id,b.sha256,b.verification_id,statement_timestamp()))
  AND EXISTS(SELECT 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
   WHERE m.workspace_id=p_workspace AND m.user_id=latest.actor_id AND m.status='active' AND m.role IN ('owner','admin')
   AND m.updated_at=latest.actor_membership_updated_at AND p.status='approved') THEN
  BEGIN
   prepared:=private.prepare_acquisition_mail_content(p_workspace,p_campaign,latest.creative_id,latest.destination_review_id,latest.company_name);
   valid:=(prepared->>'preparation_hash'=latest.preparation_hash AND prepared->'snapshot'->>'renderer_version'=latest.renderer_version);
  EXCEPTION WHEN insufficient_privilege OR serialization_failure OR object_not_in_prerequisite_state OR invalid_parameter_value THEN
   valid:=false;
  END;
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'campaign_id',p_campaign,'content_id',p_content,
  'version',coalesce(latest.version,0),'latest_review',CASE WHEN latest.id IS NULL THEN NULL ELSE to_jsonb(latest) END,
  'review_current',valid,'status',CASE WHEN latest.id IS NULL THEN 'pending_review' WHEN latest.action='withdrawn' THEN 'withdrawn'
   WHEN valid THEN 'approved' ELSE 'requires_review' END,'preparation',CASE WHEN valid THEN prepared ELSE NULL END,
  'execution_authorized',false,'checked_at',statement_timestamp());
END $$;
COMMIT;
