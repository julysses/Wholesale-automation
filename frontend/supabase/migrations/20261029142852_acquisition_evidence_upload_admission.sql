-- Local proposal only. Operational upload capacity; never storage or approval authority.
BEGIN;
CREATE TABLE private.acquisition_evidence_upload_slots (
 workspace_id uuid NOT NULL REFERENCES public.workspaces(id),
 slot smallint NOT NULL CHECK(slot IN (1,2)),
 actor_id uuid NOT NULL REFERENCES public.profiles(id),
 attempt_id uuid NOT NULL UNIQUE,
 campaign_id uuid NOT NULL, artifact_id uuid NOT NULL,
 started_at timestamptz NOT NULL CHECK(isfinite(started_at)),
 expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)),
 PRIMARY KEY(workspace_id,slot),
 FOREIGN KEY(workspace_id,campaign_id,artifact_id) REFERENCES public.acquisition_evidence_artifacts(workspace_id,campaign_id,id),
 CHECK(expires_at=started_at+interval '120 seconds')
);
ALTER TABLE private.acquisition_evidence_upload_slots ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_evidence_upload_slots FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.admit_acquisition_evidence_upload(p_attempt uuid,p_workspace uuid,p_campaign uuid,p_artifact uuid,p_purpose text)
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
    campaign_id=EXCLUDED.campaign_id,artifact_id=EXCLUDED.artifact_id,started_at=EXCLUDED.started_at,expires_at=EXCLUDED.expires_at;
 END IF;
 RETURN jsonb_build_object('attempt_id',p_attempt,'workspace_id',p_workspace,'campaign_id',p_campaign,'artifact_id',p_artifact,
  'purpose',p_purpose,'admitted',retry_at IS NULL,'checked_at',stamped,'expires_at',expiry,
  'retry_after_seconds',CASE WHEN retry_at IS NULL THEN 0 ELSE greatest(1,ceil(extract(epoch FROM retry_at-stamped))::integer) END,
  'execution_authorized',false);
END $$;
CREATE FUNCTION public.admit_acquisition_evidence_upload(p_attempt uuid,p_workspace uuid,p_campaign uuid,p_artifact uuid,p_purpose text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.admit_acquisition_evidence_upload(p_attempt,p_workspace,p_campaign,p_artifact,p_purpose)
$$;
REVOKE ALL ON FUNCTION private.admit_acquisition_evidence_upload(uuid,uuid,uuid,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON FUNCTION public.admit_acquisition_evidence_upload(uuid,uuid,uuid,uuid,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.admit_acquisition_evidence_upload(uuid,uuid,uuid,uuid,text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.admit_acquisition_evidence_upload(uuid,uuid,uuid,uuid,text) TO authenticated;
COMMIT;
