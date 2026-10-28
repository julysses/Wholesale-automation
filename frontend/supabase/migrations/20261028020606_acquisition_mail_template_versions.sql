-- Add immutable mail drafts to the existing creative master; no fulfillment.
BEGIN;
ALTER TABLE public.ad_creatives
 ADD COLUMN workspace_id uuid REFERENCES public.workspaces(id),
 ADD COLUMN acquisition_template_id uuid,
 ADD COLUMN acquisition_template_version integer,
 ADD COLUMN acquisition_mail_format text,
 ADD COLUMN acquisition_tracking_mode text,
 ADD COLUMN acquisition_created_by uuid REFERENCES public.profiles(id),
 ADD CONSTRAINT acquisition_mail_template_shape CHECK (
 (workspace_id IS NULL AND acquisition_template_id IS NULL AND acquisition_template_version IS NULL AND acquisition_mail_format IS NULL AND acquisition_tracking_mode IS NULL AND acquisition_created_by IS NULL)
 OR (workspace_id IS NOT NULL AND campaign_id IS NOT NULL AND acquisition_template_id IS NOT NULL
 AND acquisition_template_version IS NOT NULL AND acquisition_template_version>0
 AND acquisition_mail_format IS NOT NULL AND acquisition_mail_format IN ('letter','postcard')
 AND acquisition_tracking_mode IS NOT NULL AND acquisition_tracking_mode IN ('phone','landing_page')
 AND acquisition_created_by IS NOT NULL AND status IS NOT NULL AND status='draft'
 AND primary_text IS NOT NULL AND length(primary_text) BETWEEN 1 AND 20000 AND external_ad_id IS NULL AND image_url IS NULL)),
 ADD CONSTRAINT acquisition_mail_template_scope FOREIGN KEY(workspace_id,campaign_id) REFERENCES public.ad_campaigns(workspace_id,id),
 ADD CONSTRAINT acquisition_mail_template_version_unique UNIQUE(workspace_id,acquisition_template_id,acquisition_template_version);
ALTER TABLE public.ad_creatives ENABLE ROW LEVEL SECURITY;
CREATE INDEX acquisition_mail_template_workspace ON public.ad_creatives(workspace_id,id) WHERE workspace_id IS NOT NULL;
DROP POLICY IF EXISTS acquisition_legacy_boundary ON public.ad_creatives;
CREATE POLICY acquisition_mail_template_read ON public.ad_creatives AS RESTRICTIVE FOR SELECT TO authenticated
 USING(CASE WHEN workspace_id IS NULL THEN private.acquisition_legacy_access() ELSE coalesce(private.acquisition_role(workspace_id) IN ('owner','admin','operator'),false) END);
CREATE POLICY acquisition_mail_template_insert ON public.ad_creatives AS RESTRICTIVE FOR INSERT TO authenticated
 WITH CHECK(workspace_id IS NULL AND private.acquisition_legacy_access());
CREATE POLICY acquisition_mail_template_update ON public.ad_creatives AS RESTRICTIVE FOR UPDATE TO authenticated
 USING(workspace_id IS NULL AND private.acquisition_legacy_access()) WITH CHECK(workspace_id IS NULL AND private.acquisition_legacy_access());
CREATE POLICY acquisition_mail_template_delete ON public.ad_creatives AS RESTRICTIVE FOR DELETE TO authenticated
 USING(workspace_id IS NULL AND private.acquisition_legacy_access());

CREATE FUNCTION private.save_acquisition_mail_template(p_id uuid,p_workspace uuid,p_campaign uuid,p_template uuid,
 p_expected_version integer,p_name text,p_format text,p_tracking_mode text,p_body text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.ad_creatives%ROWTYPE; latest public.ad_creatives%ROWTYPE; active boolean; duplicate boolean:=false;
BEGIN
 IF auth.jwt()->>'aal' IS DISTINCT FROM 'aal2' THEN RAISE EXCEPTION 'MFA required' USING ERRCODE='42501'; END IF;
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN RAISE EXCEPTION 'Template editor required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_template IS NULL OR p_campaign IS NULL OR p_expected_version IS NULL OR p_expected_version<0 OR p_expected_version>=1000000000
 OR p_name IS NULL OR length(trim(p_name)) NOT BETWEEN 1 AND 200 OR p_body IS NULL OR length(trim(p_body)) NOT BETWEEN 1 AND 20000
 OR p_format IS NULL OR p_format NOT IN ('letter','postcard') OR p_tracking_mode IS NULL OR p_tracking_mode NOT IN ('phone','landing_page') THEN
 RAISE EXCEPTION 'Invalid template draft' USING ERRCODE='22023'; END IF;
 IF (p_tracking_mode='phone' AND strpos(p_body,'{{tracking_phone}}')=0)
 OR (p_tracking_mode='landing_page' AND strpos(p_body,'{{tracking_url}}')=0)
 OR regexp_replace(p_body,'\{\{(tracking_phone|tracking_url|property_address|company_name)\}\}','','g') ~ '[{}]' THEN
 RAISE EXCEPTION 'Tracked destination placeholder and supported fields required' USING ERRCODE='22023'; END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id JOIN auth.sessions s ON s.user_id=p.id
 WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active' AND m.role IN ('owner','admin','operator') AND p.status='approved'
 AND s.id::text=auth.jwt()->>'session_id' AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Template authority changed' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.ad_campaigns WHERE id=p_campaign AND workspace_id=p_workspace AND acquisition_channel='direct_mail' AND status='draft' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Mail campaign draft unavailable' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('mail-template-request:'||p_id::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('mail-template:'||p_workspace::text||':'||p_template::text,0));
 SELECT * INTO saved FROM public.ad_creatives WHERE id=p_id;
 IF FOUND THEN
 IF ROW(saved.workspace_id,saved.campaign_id,saved.acquisition_template_id,saved.acquisition_template_version,saved.name,saved.acquisition_mail_format,saved.acquisition_tracking_mode,saved.primary_text,saved.acquisition_created_by)
 IS DISTINCT FROM ROW(p_workspace,p_campaign,p_template,p_expected_version+1,trim(p_name),p_format,p_tracking_mode,trim(p_body),auth.uid()) THEN
 RAISE EXCEPTION 'Template request conflict' USING ERRCODE='23505'; END IF;
 duplicate:=true;
 ELSE
 SELECT * INTO latest FROM public.ad_creatives WHERE workspace_id=p_workspace AND acquisition_template_id=p_template ORDER BY acquisition_template_version DESC LIMIT 1;
 IF coalesce(latest.acquisition_template_version,0)<>p_expected_version OR (latest.id IS NOT NULL AND latest.campaign_id<>p_campaign) THEN
 RAISE EXCEPTION 'Template version changed' USING ERRCODE='40001'; END IF;
 INSERT INTO public.ad_creatives(id,workspace_id,campaign_id,acquisition_template_id,acquisition_template_version,acquisition_mail_format,acquisition_tracking_mode,acquisition_created_by,name,primary_text,status,cta_text,impressions,clicks,leads_count,total_spend,is_winner)
 VALUES(p_id,p_workspace,p_campaign,p_template,p_expected_version+1,p_format,p_tracking_mode,auth.uid(),trim(p_name),trim(p_body),'draft',NULL,NULL,NULL,NULL,NULL,NULL) RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_mail_template',p_id::text,'draft_version_saved',auth.uid()::text,jsonb_build_object('template_id',p_template,'version',saved.acquisition_template_version,'campaign_id',p_campaign,'format',p_format),p_workspace);
 END IF;
 RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'template_id',saved.acquisition_template_id,'version',saved.acquisition_template_version,'status','draft','duplicate',duplicate,'execution_authorized',false);
END $$;
CREATE FUNCTION public.save_acquisition_mail_template(p_id uuid,p_workspace uuid,p_campaign uuid,p_template uuid,p_expected_version integer,p_name text,p_format text,p_tracking_mode text,p_body text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.save_acquisition_mail_template(p_id,p_workspace,p_campaign,p_template,p_expected_version,p_name,p_format,p_tracking_mode,p_body) $$;
REVOKE ALL ON FUNCTION private.save_acquisition_mail_template(uuid,uuid,uuid,uuid,integer,text,text,text,text),public.save_acquisition_mail_template(uuid,uuid,uuid,uuid,integer,text,text,text,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.save_acquisition_mail_template(uuid,uuid,uuid,uuid,integer,text,text,text,text),public.save_acquisition_mail_template(uuid,uuid,uuid,uuid,integer,text,text,text,text) TO authenticated;

DROP TRIGGER acquisition_creative_campaign_guard ON public.ad_creatives;
CREATE FUNCTION private.protect_acquisition_mail_template() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE scoped boolean; parent_scope uuid; function_owner text;
BEGIN
 scoped:=CASE WHEN TG_OP='DELETE' THEN OLD.workspace_id IS NOT NULL ELSE NEW.workspace_id IS NOT NULL END;
 IF TG_OP='UPDATE' THEN scoped:=scoped OR OLD.workspace_id IS NOT NULL; END IF;
 IF scoped THEN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Mail drafts are immutable versions' USING ERRCODE='42501'; END IF;
 SELECT pg_get_userbyid(proowner) INTO function_owner FROM pg_proc WHERE oid='private.save_acquisition_mail_template(uuid,uuid,uuid,uuid,integer,text,text,text,text)'::regprocedure;
 IF current_user<>function_owner THEN RAISE EXCEPTION 'Use mail template function' USING ERRCODE='42501'; END IF;
 RETURN NEW;
 END IF;
 IF TG_OP<>'DELETE' AND NEW.campaign_id IS NOT NULL THEN
 SELECT workspace_id INTO parent_scope FROM public.ad_campaigns WHERE id=NEW.campaign_id FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Campaign parent unavailable' USING ERRCODE='23503'; END IF;
 IF parent_scope IS NOT NULL THEN RAISE EXCEPTION 'Reviewed acquisition campaign association required' USING ERRCODE='42501'; END IF;
 END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
REVOKE ALL ON FUNCTION private.protect_acquisition_mail_template() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER protect_acquisition_mail_template BEFORE INSERT OR UPDATE OR DELETE ON public.ad_creatives FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_mail_template();
CREATE FUNCTION private.reject_mail_template_lead_association() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE scope uuid;
BEGIN
 IF NEW.ad_creative_id IS NOT NULL THEN
 SELECT workspace_id INTO scope FROM public.ad_creatives WHERE id=NEW.ad_creative_id FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Creative parent unavailable' USING ERRCODE='23503'; END IF;
 IF scope IS NOT NULL THEN RAISE EXCEPTION 'Mail draft attribution requires reviewed tracking' USING ERRCODE='42501'; END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.reject_mail_template_lead_association() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER reject_mail_template_lead_association BEFORE INSERT OR UPDATE OF ad_creative_id ON public.leads FOR EACH ROW EXECUTE FUNCTION private.reject_mail_template_lead_association();
COMMIT;
