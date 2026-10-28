-- Reviewed inbound response destinations only; no provider configuration or mail authority.
BEGIN;
CREATE TABLE public.acquisition_mail_destination_reviews (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 campaign_id uuid NOT NULL,
 destination_id uuid NOT NULL,
 version integer NOT NULL CHECK(version BETWEEN 1 AND 1000000000),
 action text NOT NULL CHECK(action IN ('approved','withdrawn')),
 mode text NOT NULL CHECK(mode IN ('phone','landing_page')),
 value text NOT NULL CHECK(length(value) BETWEEN 1 AND 2048),
 verification_ref uuid NOT NULL,
 verification_hash text NOT NULL CHECK(verification_hash ~ '^[0-9a-f]{64}$'),
 verified_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL CHECK(expires_at>verified_at),
 review_note text NOT NULL CHECK(length(trim(review_note)) BETWEEN 20 AND 2000),
 request_hash text NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
 actor_id uuid NOT NULL REFERENCES public.profiles(id),
 actor_membership_updated_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,destination_id,version), UNIQUE(workspace_id,id),
 FOREIGN KEY(workspace_id,campaign_id) REFERENCES public.ad_campaigns(workspace_id,id)
);
CREATE INDEX acquisition_mail_destination_campaign ON public.acquisition_mail_destination_reviews(workspace_id,campaign_id,id);
ALTER TABLE public.acquisition_mail_destination_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_mail_destination_reviews FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_mail_destination_reviews TO authenticated;
CREATE POLICY acquisition_mail_destination_read ON public.acquisition_mail_destination_reviews FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE TRIGGER acquisition_mail_destination_immutable BEFORE UPDATE OR DELETE ON public.acquisition_mail_destination_reviews
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

CREATE FUNCTION private.acquisition_mail_destination_state(p_workspace uuid,p_campaign uuid,p_destination uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE latest public.acquisition_mail_destination_reviews%ROWTYPE; valid boolean:=false; active boolean;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Destination review access denied' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.ad_campaigns WHERE workspace_id=p_workspace AND id=p_campaign AND acquisition_channel='direct_mail';
 IF NOT FOUND THEN RAISE EXCEPTION 'Mail campaign unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO latest FROM public.acquisition_mail_destination_reviews
 WHERE workspace_id=p_workspace AND campaign_id=p_campaign AND destination_id=p_destination ORDER BY version DESC LIMIT 1;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton;
 IF latest.id IS NOT NULL THEN
  valid:=coalesce(active AND latest.action='approved' AND latest.verified_at<=statement_timestamp()
   AND latest.expires_at>statement_timestamp()
   AND EXISTS(SELECT 1 FROM public.workspaces WHERE id=p_workspace AND status='active')
   AND EXISTS(SELECT 1 FROM public.ad_campaigns WHERE workspace_id=p_workspace AND id=p_campaign AND status='draft')
   AND EXISTS(SELECT 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
     WHERE m.workspace_id=p_workspace AND m.user_id=latest.actor_id AND m.status='active' AND m.role IN ('owner','admin')
     AND m.updated_at=latest.actor_membership_updated_at AND p.status='approved'),false);
 END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'campaign_id',p_campaign,'destination_id',p_destination,
  'version',coalesce(latest.version,0),'latest_review',CASE WHEN latest.id IS NULL THEN NULL ELSE to_jsonb(latest) END,
  'review_current',valid,'status',CASE WHEN latest.id IS NULL THEN 'pending_review' WHEN latest.action='withdrawn' THEN 'withdrawn'
   WHEN valid THEN 'approved' ELSE 'requires_review' END,'execution_authorized',false,'checked_at',statement_timestamp());
END $$;

CREATE FUNCTION private.review_acquisition_mail_destination(p_id uuid,p_workspace uuid,p_campaign uuid,p_destination uuid,
 p_expected_version integer,p_action text,p_mode text,p_value text,p_verification_ref uuid,p_verification_hash text,
 p_verified_at timestamptz,p_expires_at timestamptz,p_note text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.acquisition_mail_destination_reviews%ROWTYPE; latest public.acquisition_mail_destination_reviews%ROWTYPE;
 active boolean; actor_updated timestamptz; request_hash text; host text;
BEGIN
 IF auth.jwt()->>'aal' IS DISTINCT FROM 'aal2' OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') THEN
  RAISE EXCEPTION 'Destination reviewer with MFA required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_campaign IS NULL OR p_destination IS NULL OR p_expected_version IS NULL OR p_expected_version NOT BETWEEN 0 AND 999999999
  OR p_action IS NULL OR p_action NOT IN ('approved','withdrawn') OR p_note IS NULL OR length(trim(p_note)) NOT BETWEEN 20 AND 2000 THEN
  RAISE EXCEPTION 'Documented destination review required' USING ERRCODE='22023'; END IF;
 IF p_action='withdrawn' AND (p_mode IS NOT NULL OR p_value IS NOT NULL OR p_verification_ref IS NOT NULL
  OR p_verification_hash IS NOT NULL OR p_verified_at IS NOT NULL OR p_expires_at IS NOT NULL) THEN
  RAISE EXCEPTION 'Withdrawal must retain prior destination evidence' USING ERRCODE='22023'; END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF p_action='approved' AND active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 SELECT m.updated_at INTO actor_updated FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id
 JOIN auth.sessions s ON s.user_id=p.id WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active'
  AND m.role IN ('owner','admin') AND p.status='approved' AND s.id::text=auth.jwt()->>'session_id'
  AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Destination review authority changed' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.ad_campaigns WHERE id=p_campaign AND workspace_id=p_workspace AND acquisition_channel='direct_mail'
  AND (p_action='withdrawn' OR status='draft') FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Mail campaign unavailable' USING ERRCODE='42501'; END IF;
 request_hash:=encode(sha256(convert_to(jsonb_build_array(p_workspace,p_campaign,p_destination,p_expected_version,p_action,
  p_mode,p_value,p_verification_ref,p_verification_hash,extract(epoch from p_verified_at),extract(epoch from p_expires_at),p_note,auth.uid())::text,'UTF8')),'hex');
 PERFORM pg_advisory_xact_lock(hashtextextended('mail-destination-request:'||p_id::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('mail-destination:'||p_workspace::text||':'||p_destination::text,0));
 SELECT * INTO saved FROM public.acquisition_mail_destination_reviews WHERE id=p_id;
 IF FOUND THEN
  IF saved.request_hash IS DISTINCT FROM request_hash THEN RAISE EXCEPTION 'Destination request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'destination_id',saved.destination_id,
   'version',saved.version,'duplicate',true,'execution_authorized',false);
 END IF;
 SELECT * INTO latest FROM public.acquisition_mail_destination_reviews WHERE workspace_id=p_workspace AND destination_id=p_destination ORDER BY version DESC LIMIT 1;
 IF coalesce(latest.version,0)<>p_expected_version OR (latest.id IS NOT NULL AND latest.campaign_id<>p_campaign) THEN
  RAISE EXCEPTION 'Destination review changed' USING ERRCODE='40001'; END IF;
 IF p_action='withdrawn' THEN
  IF latest.id IS NULL OR latest.action='withdrawn' THEN RAISE EXCEPTION 'Existing destination approval required' USING ERRCODE='55000'; END IF;
  p_mode:=latest.mode;p_value:=latest.value;p_verification_ref:=latest.verification_ref;p_verification_hash:=latest.verification_hash;
  p_verified_at:=latest.verified_at;p_expires_at:=latest.expires_at;
 ELSE
  IF p_mode IS NULL OR p_mode NOT IN ('phone','landing_page') OR p_value IS NULL OR length(p_value) NOT BETWEEN 1 AND 2048
   OR p_verification_ref IS NULL OR p_verification_hash IS NULL OR p_verification_hash !~ '^[0-9a-f]{64}$'
   OR p_verified_at IS NULL OR NOT isfinite(p_verified_at) OR p_verified_at>clock_timestamp()
   OR p_expires_at IS NULL OR NOT isfinite(p_expires_at) OR p_expires_at<=clock_timestamp() OR p_expires_at<=p_verified_at THEN
   RAISE EXCEPTION 'Current destination verification evidence required' USING ERRCODE='22023'; END IF;
  IF p_mode='phone' AND p_value !~ '^\+[1-9][0-9]{7,14}$' THEN RAISE EXCEPTION 'Normalized tracked phone required' USING ERRCODE='22023'; END IF;
  IF p_mode='landing_page' THEN
   -- Conservative syntax only. Reviewer evidence must prove control and actual routing.
   IF p_value !~ '^https://[a-z0-9.-]+(/[^[:space:]]*)?$' OR p_value ~ '[[:cntrl:][:space:]%?#{}<>"\\]' THEN
    RAISE EXCEPTION 'Public HTTPS tracked destination required' USING ERRCODE='22023'; END IF;
   host:=split_part(split_part(p_value,'://',2),'/',1);
   IF host !~ '^[a-z0-9]+([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]+([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,63}$'
    OR host ~ '\.(localhost|local|internal|test|invalid|example)$' THEN
    RAISE EXCEPTION 'Public hostname required' USING ERRCODE='22023'; END IF;
  END IF;
 END IF;
 INSERT INTO public.acquisition_mail_destination_reviews(id,workspace_id,campaign_id,destination_id,version,action,mode,value,
  verification_ref,verification_hash,verified_at,expires_at,review_note,request_hash,actor_id,actor_membership_updated_at)
 VALUES(p_id,p_workspace,p_campaign,p_destination,p_expected_version+1,p_action,p_mode,p_value,p_verification_ref,
  p_verification_hash,p_verified_at,p_expires_at,p_note,request_hash,auth.uid(),actor_updated) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,workspace_id,new_value)
 VALUES('acquisition_mail_destination',p_destination::text,p_action,auth.uid()::text,p_workspace,
  jsonb_build_object('review_id',p_id,'version',saved.version,'campaign_id',p_campaign,'mode',p_mode,'execution_authorized',false));
 RETURN jsonb_build_object('review_id',saved.id,'workspace_id',saved.workspace_id,'destination_id',saved.destination_id,
  'version',saved.version,'duplicate',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.acquisition_mail_destination_state(p_workspace uuid,p_campaign uuid,p_destination uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_mail_destination_state(p_workspace,p_campaign,p_destination) $$;
CREATE FUNCTION public.review_acquisition_mail_destination(p_id uuid,p_workspace uuid,p_campaign uuid,p_destination uuid,
 p_expected_version integer,p_action text,p_mode text,p_value text,p_verification_ref uuid,p_verification_hash text,p_verified_at timestamptz,p_expires_at timestamptz,p_note text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.review_acquisition_mail_destination(p_id,p_workspace,p_campaign,p_destination,
 p_expected_version,p_action,p_mode,p_value,p_verification_ref,p_verification_hash,p_verified_at,p_expires_at,p_note) $$;
REVOKE ALL ON FUNCTION private.acquisition_mail_destination_state(uuid,uuid,uuid),public.acquisition_mail_destination_state(uuid,uuid,uuid),
 private.review_acquisition_mail_destination(uuid,uuid,uuid,uuid,integer,text,text,text,uuid,text,timestamptz,timestamptz,text),
 public.review_acquisition_mail_destination(uuid,uuid,uuid,uuid,integer,text,text,text,uuid,text,timestamptz,timestamptz,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_mail_destination_state(uuid,uuid,uuid),public.acquisition_mail_destination_state(uuid,uuid,uuid),
 private.review_acquisition_mail_destination(uuid,uuid,uuid,uuid,integer,text,text,text,uuid,text,timestamptz,timestamptz,text),
 public.review_acquisition_mail_destination(uuid,uuid,uuid,uuid,integer,text,text,text,uuid,text,timestamptz,timestamptz,text) TO authenticated;
COMMIT;
