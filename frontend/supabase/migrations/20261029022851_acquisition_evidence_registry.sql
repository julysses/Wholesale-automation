-- Local proposal only. Registers expectations, never bytes, content approval or execution authority.
BEGIN;
CREATE TABLE private.acquisition_evidence_policies (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES public.workspaces(id),
 purpose text NOT NULL CHECK(purpose IN ('mail_content','mail_destination')),
 version integer NOT NULL CHECK(version BETWEEN 1 AND 1000000000),
 retention_seconds integer NOT NULL CHECK(retention_seconds>0),
 valid_from timestamptz NOT NULL CHECK(isfinite(valid_from)), valid_until timestamptz NOT NULL CHECK(isfinite(valid_until)),
 approval_ref uuid NOT NULL, reviewed_by uuid NOT NULL REFERENCES public.profiles(id),
 reviewed_at timestamptz NOT NULL CHECK(isfinite(reviewed_at)), revoked_at timestamptz CHECK(isfinite(revoked_at)),
 UNIQUE(workspace_id,purpose,version), UNIQUE(workspace_id,id),
 CHECK(valid_from<valid_until AND reviewed_at<=valid_from), CHECK(revoked_at IS NULL OR revoked_at>=reviewed_at)
);
-- Deployment-controlled reviewed configuration: intentionally empty and inaccessible to application roles.
ALTER TABLE private.acquisition_evidence_policies ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_evidence_policies FROM PUBLIC,anon,authenticated,service_role;

CREATE TABLE public.acquisition_evidence_artifacts (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, campaign_id uuid NOT NULL,
 purpose text NOT NULL CHECK(purpose IN ('mail_content','mail_destination')),
 expected_sha256 text NOT NULL CHECK(expected_sha256 ~ '^[0-9a-f]{64}$'),
 expected_byte_size integer NOT NULL CHECK(expected_byte_size BETWEEN 1 AND 10485760),
 media_type text NOT NULL CHECK(media_type IN ('application/pdf','image/png','image/jpeg','text/plain')),
 retention_policy_id uuid NOT NULL, retain_until timestamptz NOT NULL CHECK(isfinite(retain_until)),
 provenance_note text NOT NULL CHECK(length(trim(provenance_note)) BETWEEN 20 AND 2000),
 created_by uuid NOT NULL REFERENCES public.profiles(id), actor_membership_updated_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), request_hash text NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
 UNIQUE(workspace_id,id), UNIQUE(workspace_id,campaign_id,id), CHECK(retain_until>created_at),
 FOREIGN KEY(workspace_id,campaign_id) REFERENCES public.ad_campaigns(workspace_id,id),
 FOREIGN KEY(workspace_id,retention_policy_id) REFERENCES private.acquisition_evidence_policies(workspace_id,id)
);
CREATE INDEX acquisition_evidence_campaign ON public.acquisition_evidence_artifacts(workspace_id,campaign_id,id);
CREATE INDEX acquisition_evidence_retention ON public.acquisition_evidence_artifacts(retain_until,id);
CREATE TABLE public.acquisition_evidence_revocations (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, campaign_id uuid NOT NULL, artifact_id uuid NOT NULL,
 reason text NOT NULL CHECK(length(trim(reason)) BETWEEN 20 AND 2000),
 actor_id uuid NOT NULL REFERENCES public.profiles(id), actor_membership_updated_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(), request_hash text NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
 UNIQUE(workspace_id,artifact_id),
 FOREIGN KEY(workspace_id,campaign_id,artifact_id) REFERENCES public.acquisition_evidence_artifacts(workspace_id,campaign_id,id)
);
CREATE INDEX acquisition_evidence_revocation_campaign ON public.acquisition_evidence_revocations(workspace_id,campaign_id,id);
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['acquisition_evidence_artifacts','acquisition_evidence_revocations'] LOOP
  EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',t);
  EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC,anon,authenticated,service_role',t);
  EXECUTE format('GRANT SELECT ON public.%I TO authenticated',t);
  EXECUTE format('CREATE POLICY acquisition_evidence_read ON public.%I FOR SELECT TO authenticated USING(private.acquisition_role(workspace_id) IN (''owner'',''admin'',''operator''))',t);
  EXECUTE format('CREATE TRIGGER acquisition_evidence_immutable BEFORE UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact()',t);
 END LOOP;
END $$;

CREATE FUNCTION private.register_acquisition_evidence(p_id uuid,p_workspace uuid,p_campaign uuid,p_purpose text,
 p_sha256 text,p_byte_size integer,p_media_type text,p_policy uuid,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_evidence_artifacts%ROWTYPE; policy private.acquisition_evidence_policies%ROWTYPE;
 actor_updated timestamptz; session_expires timestamptz; active boolean; fingerprint text; stamped timestamptz;
BEGIN
 IF auth.jwt()->>'aal' IS DISTINCT FROM 'aal2' OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Evidence registration authority required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_campaign IS NULL OR p_purpose IS NULL OR p_purpose NOT IN ('mail_content','mail_destination')
  OR p_sha256 IS NULL OR p_sha256 !~ '^[0-9a-f]{64}$' OR p_byte_size IS NULL OR p_byte_size NOT BETWEEN 1 AND 10485760
  OR p_media_type IS NULL OR p_media_type NOT IN ('application/pdf','image/png','image/jpeg','text/plain')
  OR p_policy IS NULL OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 20 AND 2000 THEN
  RAISE EXCEPTION 'Bounded evidence expectations and provenance required' USING ERRCODE='22023'; END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 SELECT m.updated_at,s.not_after INTO actor_updated,session_expires FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
 JOIN auth.sessions s ON s.user_id=p.id WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active'
  AND m.role IN ('owner','admin','operator') AND p.status='approved' AND s.id::text=auth.jwt()->>'session_id'
  AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Evidence registration authority changed' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.ad_campaigns WHERE workspace_id=p_workspace AND id=p_campaign AND acquisition_channel='direct_mail' AND status='draft' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Mail campaign unavailable' USING ERRCODE='42501'; END IF;
 fingerprint:=encode(sha256(convert_to(jsonb_build_array(p_workspace,p_campaign,p_purpose,p_sha256,p_byte_size,p_media_type,p_policy,p_note,auth.uid())::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||p_id::text,0));
 IF session_expires IS NOT NULL AND session_expires<=clock_timestamp() THEN RAISE EXCEPTION 'Evidence session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_evidence_artifacts WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Evidence request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('artifact_id',saved.id,'workspace_id',saved.workspace_id,'retain_until',saved.retain_until,
   'duplicate',true,'bytes_verified',false,'execution_authorized',false);
 END IF;
 SELECT * INTO policy FROM private.acquisition_evidence_policies WHERE id=p_policy AND workspace_id=p_workspace AND purpose=p_purpose FOR SHARE;
 stamped:=clock_timestamp();
 IF session_expires IS NOT NULL AND session_expires<=stamped THEN RAISE EXCEPTION 'Evidence session expired' USING ERRCODE='42501'; END IF;
 IF NOT FOUND OR policy.revoked_at IS NOT NULL OR NOT(policy.valid_from<=stamped AND stamped<policy.valid_until) THEN
  RAISE EXCEPTION 'Reviewed current retention policy required' USING ERRCODE='55000'; END IF;
 INSERT INTO public.acquisition_evidence_artifacts(id,workspace_id,campaign_id,purpose,expected_sha256,expected_byte_size,
  media_type,retention_policy_id,retain_until,provenance_note,created_by,actor_membership_updated_at,created_at,request_hash)
 VALUES(p_id,p_workspace,p_campaign,p_purpose,p_sha256,p_byte_size,p_media_type,p_policy,
  stamped+make_interval(secs=>policy.retention_seconds),p_note,auth.uid(),actor_updated,stamped,fingerprint) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_evidence',p_id::text,'registered',auth.uid()::text,p_workspace,
  jsonb_build_object('campaign_id',p_campaign,'purpose',p_purpose,'policy_id',p_policy,'bytes_verified',false,'execution_authorized',false));
 RETURN jsonb_build_object('artifact_id',saved.id,'workspace_id',saved.workspace_id,'retain_until',saved.retain_until,
  'duplicate',false,'bytes_verified',false,'execution_authorized',false);
END $$;

CREATE FUNCTION private.revoke_acquisition_evidence(p_id uuid,p_workspace uuid,p_campaign uuid,p_artifact uuid,p_reason text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_evidence_revocations%ROWTYPE; actor_updated timestamptz; session_expires timestamptz; fingerprint text;
BEGIN
 IF auth.jwt()->>'aal' IS DISTINCT FROM 'aal2' OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') THEN
  RAISE EXCEPTION 'Evidence revocation authority required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_campaign IS NULL OR p_artifact IS NULL OR p_reason IS NULL OR length(trim(p_reason)) NOT BETWEEN 20 AND 2000 THEN
  RAISE EXCEPTION 'Documented revocation required' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 SELECT m.updated_at,s.not_after INTO actor_updated,session_expires FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
 JOIN auth.sessions s ON s.user_id=p.id WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active'
  AND m.role IN ('owner','admin') AND p.status='approved' AND s.id::text=auth.jwt()->>'session_id'
  AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Evidence revocation authority changed' USING ERRCODE='42501'; END IF;
 fingerprint:=encode(sha256(convert_to(jsonb_build_array(p_workspace,p_campaign,p_artifact,p_reason,auth.uid())::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-revocation:'||p_id::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('evidence-artifact:'||p_artifact::text,0));
 IF session_expires IS NOT NULL AND session_expires<=clock_timestamp() THEN RAISE EXCEPTION 'Evidence session expired' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND campaign_id=p_campaign AND id=p_artifact;
 IF NOT FOUND THEN RAISE EXCEPTION 'Evidence artifact unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_evidence_revocations WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM fingerprint THEN RAISE EXCEPTION 'Revocation request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('revocation_id',saved.id,'artifact_id',saved.artifact_id,'workspace_id',saved.workspace_id,'duplicate',true,'execution_authorized',false);
 END IF;
 INSERT INTO public.acquisition_evidence_revocations(id,workspace_id,campaign_id,artifact_id,reason,actor_id,actor_membership_updated_at,request_hash)
 VALUES(p_id,p_workspace,p_campaign,p_artifact,p_reason,auth.uid(),actor_updated,fingerprint) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_evidence',p_artifact::text,'revoked',auth.uid()::text,p_workspace,jsonb_build_object('revocation_id',p_id,'campaign_id',p_campaign,'execution_authorized',false));
 RETURN jsonb_build_object('revocation_id',saved.id,'artifact_id',saved.artifact_id,'workspace_id',saved.workspace_id,'duplicate',false,'execution_authorized',false);
END $$;

CREATE FUNCTION private.acquisition_evidence_state(p_workspace uuid,p_campaign uuid,p_artifact uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE artifact public.acquisition_evidence_artifacts%ROWTYPE; revocation public.acquisition_evidence_revocations%ROWTYPE; policy_current boolean;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Evidence access denied' USING ERRCODE='42501'; END IF;
 SELECT * INTO artifact FROM public.acquisition_evidence_artifacts WHERE workspace_id=p_workspace AND campaign_id=p_campaign AND id=p_artifact;
 IF NOT FOUND THEN RAISE EXCEPTION 'Evidence artifact unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO revocation FROM public.acquisition_evidence_revocations WHERE workspace_id=p_workspace AND artifact_id=p_artifact;
 SELECT revoked_at IS NULL AND valid_from<=statement_timestamp() AND valid_until>statement_timestamp() INTO policy_current
 FROM private.acquisition_evidence_policies WHERE id=artifact.retention_policy_id AND workspace_id=p_workspace AND purpose=artifact.purpose;
 RETURN jsonb_build_object('workspace_id',p_workspace,'campaign_id',p_campaign,'artifact_id',p_artifact,
  'purpose',artifact.purpose,'expected_sha256',artifact.expected_sha256,'expected_byte_size',artifact.expected_byte_size,
  'media_type',artifact.media_type,'created_at',artifact.created_at,'retain_until',artifact.retain_until,
  'retention_policy_id',artifact.retention_policy_id,'revoked_at',revocation.created_at,
  'status',CASE WHEN revocation.id IS NOT NULL THEN 'revoked' WHEN artifact.retain_until<=statement_timestamp() THEN 'expired'
   WHEN policy_current IS DISTINCT FROM true THEN 'policy_review_required' ELSE 'pending_verification' END,
  'bytes_verified',false,'content_approved',false,'execution_authorized',false,'checked_at',statement_timestamp());
END $$;
CREATE FUNCTION public.register_acquisition_evidence(p_id uuid,p_workspace uuid,p_campaign uuid,p_purpose text,p_sha256 text,p_byte_size integer,p_media_type text,p_policy uuid,p_note text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.register_acquisition_evidence(p_id,p_workspace,p_campaign,p_purpose,p_sha256,p_byte_size,p_media_type,p_policy,p_note) $$;
CREATE FUNCTION public.revoke_acquisition_evidence(p_id uuid,p_workspace uuid,p_campaign uuid,p_artifact uuid,p_reason text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.revoke_acquisition_evidence(p_id,p_workspace,p_campaign,p_artifact,p_reason) $$;
CREATE FUNCTION public.acquisition_evidence_state(p_workspace uuid,p_campaign uuid,p_artifact uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_evidence_state(p_workspace,p_campaign,p_artifact) $$;
DO $$ DECLARE signature text; BEGIN
 FOREACH signature IN ARRAY ARRAY['register_acquisition_evidence(uuid,uuid,uuid,text,text,integer,text,uuid,text)',
  'revoke_acquisition_evidence(uuid,uuid,uuid,uuid,text)','acquisition_evidence_state(uuid,uuid,uuid)'] LOOP
  EXECUTE 'REVOKE ALL ON FUNCTION private.'||signature||' FROM PUBLIC,anon,authenticated,service_role';
  EXECUTE 'REVOKE ALL ON FUNCTION public.'||signature||' FROM PUBLIC,anon,authenticated,service_role';
  EXECUTE 'GRANT EXECUTE ON FUNCTION private.'||signature||' TO authenticated';
  EXECUTE 'GRANT EXECUTE ON FUNCTION public.'||signature||' TO authenticated';
 END LOOP;
END $$;
COMMIT;
