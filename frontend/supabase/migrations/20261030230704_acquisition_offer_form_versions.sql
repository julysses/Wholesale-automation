-- Version the existing form master. Registration is preparation, never publication.
BEGIN;
CREATE TABLE private.acquisition_form_families (
 form_key text PRIMARY KEY CHECK(form_key ~ '^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$'),
 workspace_id uuid NOT NULL,
 campaign_id uuid NOT NULL,
 UNIQUE(workspace_id,campaign_id,form_key),
 FOREIGN KEY(workspace_id,campaign_id) REFERENCES public.ad_campaigns(workspace_id,id)
);
ALTER TABLE private.acquisition_form_families ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_form_families FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION private.preserve_acquisition_form_family() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN RAISE EXCEPTION 'Form routing identity is immutable' USING ERRCODE='42501'; END $$;
REVOKE ALL ON FUNCTION private.preserve_acquisition_form_family() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_form_family_immutable BEFORE UPDATE OR DELETE ON private.acquisition_form_families
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_form_family();

ALTER TABLE public.lead_form_configs
 ADD COLUMN workspace_id uuid REFERENCES public.workspaces(id),
 ADD COLUMN acquisition_form_key text,
 ADD COLUMN acquisition_form_revision integer,
 ADD COLUMN acquisition_form_version text,
 ADD COLUMN acquisition_form_definition jsonb,
 ADD COLUMN acquisition_definition_hash text,
 ADD COLUMN acquisition_created_by uuid REFERENCES public.profiles(id),
 ADD CONSTRAINT acquisition_form_scope FOREIGN KEY(workspace_id,campaign_id,acquisition_form_key)
 REFERENCES private.acquisition_form_families(workspace_id,campaign_id,form_key),
 ADD CONSTRAINT acquisition_form_revision_unique UNIQUE(acquisition_form_key,acquisition_form_revision),
 ADD CONSTRAINT acquisition_form_version_unique UNIQUE(acquisition_form_key,acquisition_form_version),
 ADD CONSTRAINT acquisition_form_shape CHECK(
  (workspace_id IS NULL AND acquisition_form_key IS NULL AND acquisition_form_revision IS NULL
   AND acquisition_form_version IS NULL AND acquisition_form_definition IS NULL AND acquisition_definition_hash IS NULL AND acquisition_created_by IS NULL)
  OR (workspace_id IS NOT NULL AND campaign_id IS NOT NULL AND acquisition_form_key IS NOT NULL
   AND acquisition_form_revision IS NOT NULL AND acquisition_form_revision>0
   AND acquisition_form_version IS NOT NULL AND acquisition_form_version ~ '^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$'
   AND acquisition_form_definition IS NOT NULL AND jsonb_typeof(acquisition_form_definition)='object'
   AND acquisition_definition_hash IS NOT NULL AND acquisition_definition_hash ~ '^[0-9a-f]{64}$'
   AND acquisition_created_by IS NOT NULL AND active IS FALSE
   AND send_confirmation_sms IS FALSE AND send_confirmation_email IS FALSE AND redirect_url IS NULL));
CREATE INDEX acquisition_form_workspace_idx ON public.lead_form_configs(workspace_id,id) WHERE workspace_id IS NOT NULL;
ALTER TABLE public.lead_form_configs ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS acquisition_legacy_boundary ON public.lead_form_configs;
CREATE POLICY acquisition_form_read ON public.lead_form_configs AS RESTRICTIVE FOR SELECT TO authenticated
 USING(CASE WHEN workspace_id IS NULL THEN private.acquisition_legacy_access()
 ELSE coalesce(private.acquisition_role(workspace_id) IN ('owner','admin','operator'),false) END);
CREATE POLICY acquisition_form_anon_read ON public.lead_form_configs AS RESTRICTIVE FOR SELECT TO anon USING(workspace_id IS NULL);
CREATE POLICY acquisition_form_insert ON public.lead_form_configs AS RESTRICTIVE FOR INSERT TO authenticated
 WITH CHECK(workspace_id IS NULL AND private.acquisition_legacy_access());
CREATE POLICY acquisition_form_update ON public.lead_form_configs AS RESTRICTIVE FOR UPDATE TO authenticated
 USING(workspace_id IS NULL AND private.acquisition_legacy_access()) WITH CHECK(workspace_id IS NULL AND private.acquisition_legacy_access());
CREATE POLICY acquisition_form_delete ON public.lead_form_configs AS RESTRICTIVE FOR DELETE TO authenticated
 USING(workspace_id IS NULL AND private.acquisition_legacy_access());

CREATE FUNCTION private.save_acquisition_offer_form(p_id uuid,p_workspace uuid,p_campaign uuid,p_expected_revision integer,p_definition jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.lead_form_configs%ROWTYPE; family private.acquisition_form_families%ROWTYPE;
 latest integer; active boolean; duplicate boolean:=false; session_expires timestamptz; key text;
 definition_hash text;
BEGIN
 IF auth.jwt()->>'role' IS DISTINCT FROM 'authenticated' OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2'
 OR coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') THEN
 RAISE EXCEPTION 'Form administrator with MFA required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_workspace IS NULL OR p_campaign IS NULL OR p_expected_revision IS NULL
 OR p_expected_revision<0 OR p_expected_revision>=1000000000 OR jsonb_typeof(p_definition) IS DISTINCT FROM 'object' THEN
 RAISE EXCEPTION 'Invalid form draft' USING ERRCODE='22023'; END IF;
 IF (SELECT count(*) FROM jsonb_object_keys(p_definition))<>5
 OR NOT p_definition ?& ARRAY['form_key','version','privacy_acknowledged','human_callback_requested','email_reply_requested'] THEN
 RAISE EXCEPTION 'Exact form definition required' USING ERRCODE='22023'; END IF;
 FOR key IN SELECT jsonb_object_keys(p_definition) LOOP
 IF jsonb_typeof(p_definition->key) IS DISTINCT FROM 'string' OR length(trim(p_definition->>key))=0 OR length(p_definition->>key)>4000 THEN
 RAISE EXCEPTION 'Invalid form wording' USING ERRCODE='22023'; END IF;
 END LOOP;
 IF p_definition->>'form_key' !~ '^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$' OR p_definition->>'version' !~ '^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$' THEN
 RAISE EXCEPTION 'Invalid form identity' USING ERRCODE='22023'; END IF;
 definition_hash:=encode(sha256(convert_to(p_definition::text,'UTF8')),'hex');
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 SELECT s.not_after INTO session_expires FROM public.workspace_memberships m
 JOIN public.profiles p ON p.id=m.user_id JOIN auth.sessions s ON s.user_id=p.id
 WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active' AND m.role IN ('owner','admin') AND p.status='approved'
 AND s.id::text=auth.jwt()->>'session_id' AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Form authority changed' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.ad_campaigns WHERE id=p_campaign AND workspace_id=p_workspace AND acquisition_channel='online_offer' AND status='draft' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Online offer campaign unavailable' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('offer-form-request:'||p_id::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('offer-form:'||(p_definition->>'form_key'),0));
 -- Time can pass while either serialization lock waits; statement time is unsafe.
 IF session_expires IS NOT NULL AND session_expires<=clock_timestamp() THEN
 RAISE EXCEPTION 'Form session expired' USING ERRCODE='42501'; END IF;
 SELECT * INTO family FROM private.acquisition_form_families WHERE form_key=p_definition->>'form_key';
 IF FOUND AND ROW(family.workspace_id,family.campaign_id) IS DISTINCT FROM ROW(p_workspace,p_campaign) THEN
 RAISE EXCEPTION 'Form routing identity unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.lead_form_configs WHERE id=p_id;
 IF FOUND THEN
 IF ROW(saved.workspace_id,saved.campaign_id,saved.acquisition_form_revision,saved.acquisition_form_definition,saved.acquisition_created_by)
 IS DISTINCT FROM ROW(p_workspace,p_campaign,p_expected_revision+1,p_definition,auth.uid()) THEN
 RAISE EXCEPTION 'Form request conflict' USING ERRCODE='23505'; END IF;
 duplicate:=true;
 ELSE
 SELECT max(acquisition_form_revision) INTO latest FROM public.lead_form_configs WHERE acquisition_form_key=p_definition->>'form_key';
 IF coalesce(latest,0)<>p_expected_revision THEN RAISE EXCEPTION 'Form version changed' USING ERRCODE='40001'; END IF;
 IF family.form_key IS NULL THEN
 INSERT INTO private.acquisition_form_families(form_key,workspace_id,campaign_id) VALUES(p_definition->>'form_key',p_workspace,p_campaign);
 END IF;
 INSERT INTO public.lead_form_configs(id,name,slug,campaign_id,workspace_id,acquisition_form_key,acquisition_form_revision,
 acquisition_form_version,acquisition_form_definition,acquisition_definition_hash,acquisition_created_by,
 active,send_confirmation_sms,send_confirmation_email,questions,redirect_url,headline,subheadline,brand_color,logo_url,thank_you_message)
 VALUES(p_id,'Seller offer request','acquisition-draft-'||p_id::text,p_campaign,p_workspace,p_definition->>'form_key',p_expected_revision+1,
 p_definition->>'version',p_definition,definition_hash,auth.uid(),false,false,false,'[]'::jsonb,NULL,
 'Request an offer',NULL,'#1B3A5C',NULL,'Thank you. Hilltop will review your property.') RETURNING * INTO saved;
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_offer_form',p_id::text,'draft_version_saved',auth.uid()::text,
 jsonb_build_object('form_key',saved.acquisition_form_key,'revision',saved.acquisition_form_revision,'version',saved.acquisition_form_version,
 'campaign_id',p_campaign,'definition_hash',definition_hash,'status','draft'),p_workspace);
 END IF;
 RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'campaign_id',saved.campaign_id,
 'form_key',saved.acquisition_form_key,'revision',saved.acquisition_form_revision,'version',saved.acquisition_form_version,
 'definition_hash',saved.acquisition_definition_hash,'status','draft','duplicate',duplicate,'public_enabled',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.save_acquisition_offer_form(p_id uuid,p_workspace uuid,p_campaign uuid,p_expected_revision integer,p_definition jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$
 SELECT private.save_acquisition_offer_form(p_id,p_workspace,p_campaign,p_expected_revision,p_definition)
$$;
REVOKE ALL ON FUNCTION private.save_acquisition_offer_form(uuid,uuid,uuid,integer,jsonb),public.save_acquisition_offer_form(uuid,uuid,uuid,integer,jsonb)
 FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.save_acquisition_offer_form(uuid,uuid,uuid,integer,jsonb),public.save_acquisition_offer_form(uuid,uuid,uuid,integer,jsonb) TO authenticated;

DROP TRIGGER acquisition_form_campaign_guard ON public.lead_form_configs;
CREATE FUNCTION private.protect_acquisition_offer_form() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE scoped boolean; parent_scope uuid; function_owner text;
BEGIN
 scoped:=CASE WHEN TG_OP='DELETE' THEN OLD.workspace_id IS NOT NULL ELSE NEW.workspace_id IS NOT NULL END;
 IF TG_OP='UPDATE' THEN scoped:=scoped OR OLD.workspace_id IS NOT NULL; END IF;
 IF scoped THEN
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Form drafts are immutable versions' USING ERRCODE='42501'; END IF;
 SELECT pg_get_userbyid(proowner) INTO function_owner FROM pg_proc WHERE oid='private.save_acquisition_offer_form(uuid,uuid,uuid,integer,jsonb)'::regprocedure;
 IF current_user<>function_owner THEN RAISE EXCEPTION 'Use acquisition form function' USING ERRCODE='42501'; END IF;
 RETURN NEW;
 END IF;
 IF TG_OP<>'DELETE' AND NEW.campaign_id IS NOT NULL THEN
 SELECT workspace_id INTO parent_scope FROM public.ad_campaigns WHERE id=NEW.campaign_id FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Campaign parent unavailable' USING ERRCODE='23503'; END IF;
 IF parent_scope IS NOT NULL THEN RAISE EXCEPTION 'Reviewed acquisition campaign association required' USING ERRCODE='42501'; END IF;
 END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
REVOKE ALL ON FUNCTION private.protect_acquisition_offer_form() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER protect_acquisition_offer_form BEFORE INSERT OR UPDATE OR DELETE ON public.lead_form_configs
 FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_offer_form();
-- The legacy finalizer accepts form IDs and must never use acquisition versions.
CREATE FUNCTION private.reject_acquisition_form_submission() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE scope uuid;
BEGIN
 IF NEW.form_id IS NOT NULL THEN
 SELECT workspace_id INTO scope FROM public.lead_form_configs WHERE id=NEW.form_id FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Form parent unavailable' USING ERRCODE='23503'; END IF;
 IF scope IS NOT NULL THEN RAISE EXCEPTION 'Use acquisition submission workflow' USING ERRCODE='42501'; END IF;
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.reject_acquisition_form_submission() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER reject_acquisition_form_submission BEFORE INSERT OR UPDATE OF form_id ON public.lead_form_submissions
 FOR EACH ROW EXECUTE FUNCTION private.reject_acquisition_form_submission();
COMMIT;
