-- Immutable content decisions; these do not approve campaigns, recipients or fulfillment.
BEGIN;
ALTER TABLE public.ad_creatives ADD CONSTRAINT acquisition_creative_workspace_id UNIQUE(workspace_id,id);
CREATE TABLE public.acquisition_mail_content_reviews (
 id uuid PRIMARY KEY, workspace_id uuid NOT NULL, campaign_id uuid NOT NULL, content_id uuid NOT NULL,
 version integer NOT NULL CHECK(version BETWEEN 1 AND 1000000000),
 action text NOT NULL CHECK(action IN ('approved','withdrawn')),
 creative_id uuid NOT NULL, destination_review_id uuid NOT NULL,
 company_name text NOT NULL CHECK(length(trim(company_name)) BETWEEN 1 AND 200),
 renderer_version text NOT NULL, preparation_hash text NOT NULL CHECK(preparation_hash ~ '^[0-9a-f]{64}$'),
 evidence_ref uuid NOT NULL, evidence_hash text NOT NULL CHECK(evidence_hash ~ '^[0-9a-f]{64}$'),
 expires_at timestamptz NOT NULL CHECK(isfinite(expires_at)),
 review_note text NOT NULL CHECK(length(trim(review_note)) BETWEEN 20 AND 2000),
 actor_id uuid NOT NULL REFERENCES public.profiles(id), actor_membership_updated_at timestamptz NOT NULL,
 request_hash text NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'), created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,content_id,version), UNIQUE(workspace_id,id),
 FOREIGN KEY(workspace_id,campaign_id) REFERENCES public.ad_campaigns(workspace_id,id),
 FOREIGN KEY(workspace_id,creative_id) REFERENCES public.ad_creatives(workspace_id,id),
 FOREIGN KEY(workspace_id,destination_review_id) REFERENCES public.acquisition_mail_destination_reviews(workspace_id,id)
);
CREATE INDEX acquisition_mail_content_campaign ON public.acquisition_mail_content_reviews(workspace_id,campaign_id,id);
ALTER TABLE public.acquisition_mail_content_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_mail_content_reviews FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_mail_content_reviews TO authenticated;
CREATE POLICY acquisition_mail_content_read ON public.acquisition_mail_content_reviews FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE TRIGGER acquisition_mail_content_immutable BEFORE UPDATE OR DELETE ON public.acquisition_mail_content_reviews
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

CREATE FUNCTION private.review_acquisition_mail_content(p_id uuid,p_workspace uuid,p_campaign uuid,p_content uuid,
 p_expected_version integer,p_action text,p_creative uuid,p_destination_review uuid,p_company_name text,
 p_preparation_hash text,p_evidence_ref uuid,p_evidence_hash text,p_expires_at timestamptz,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_mail_content_reviews%ROWTYPE; latest public.acquisition_mail_content_reviews%ROWTYPE;
 active boolean; actor_updated timestamptz; request_hash text; prepared jsonb; renderer text;
 template_id uuid; destination_id uuid; destination_actor uuid;
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
 SELECT m.updated_at INTO actor_updated FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
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
 END IF;
 INSERT INTO public.acquisition_mail_content_reviews(id,workspace_id,campaign_id,content_id,version,action,
  creative_id,destination_review_id,company_name,renderer_version,preparation_hash,evidence_ref,evidence_hash,expires_at,
  review_note,actor_id,actor_membership_updated_at,request_hash)
 VALUES(p_id,p_workspace,p_campaign,p_content,p_expected_version+1,p_action,p_creative,p_destination_review,p_company_name,
  renderer,p_preparation_hash,p_evidence_ref,p_evidence_hash,p_expires_at,p_note,auth.uid(),actor_updated,request_hash) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_mail_content',p_content::text,p_action,auth.uid()::text,p_workspace,
  jsonb_build_object('review_id',p_id,'version',saved.version,'campaign_id',p_campaign,'creative_id',p_creative,
   'destination_review_id',p_destination_review,'execution_authorized',false));
 RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'content_id',saved.content_id,
  'version',saved.version,'duplicate',false,'execution_authorized',false);
END $$;

CREATE FUNCTION private.acquisition_mail_content_state(p_workspace uuid,p_campaign uuid,p_content uuid)
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
CREATE FUNCTION public.review_acquisition_mail_content(p_id uuid,p_workspace uuid,p_campaign uuid,p_content uuid,
 p_expected_version integer,p_action text,p_creative uuid,p_destination_review uuid,p_company_name text,
 p_preparation_hash text,p_evidence_ref uuid,p_evidence_hash text,p_expires_at timestamptz,p_note text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.review_acquisition_mail_content(p_id,p_workspace,p_campaign,p_content,p_expected_version,p_action,
 p_creative,p_destination_review,p_company_name,p_preparation_hash,p_evidence_ref,p_evidence_hash,p_expires_at,p_note)
$$;
CREATE FUNCTION public.acquisition_mail_content_state(p_workspace uuid,p_campaign uuid,p_content uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_mail_content_state(p_workspace,p_campaign,p_content) $$;
REVOKE ALL ON FUNCTION private.review_acquisition_mail_content(uuid,uuid,uuid,uuid,integer,text,uuid,uuid,text,text,uuid,text,timestamptz,text),
 public.review_acquisition_mail_content(uuid,uuid,uuid,uuid,integer,text,uuid,uuid,text,text,uuid,text,timestamptz,text),
 private.acquisition_mail_content_state(uuid,uuid,uuid),public.acquisition_mail_content_state(uuid,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.review_acquisition_mail_content(uuid,uuid,uuid,uuid,integer,text,uuid,uuid,text,text,uuid,text,timestamptz,text),
 public.review_acquisition_mail_content(uuid,uuid,uuid,uuid,integer,text,uuid,uuid,text,text,uuid,text,timestamptz,text),
 private.acquisition_mail_content_state(uuid,uuid,uuid),public.acquisition_mail_content_state(uuid,uuid,uuid) TO authenticated;
COMMIT;
