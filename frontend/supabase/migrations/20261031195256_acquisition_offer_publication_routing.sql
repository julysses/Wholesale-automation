-- Inert publication configuration over immutable form versions. No public HTTP route.
BEGIN;
ALTER TABLE public.lead_form_configs ADD CONSTRAINT acquisition_form_publication_identity
 UNIQUE(id,workspace_id,campaign_id,acquisition_form_key);
CREATE TABLE private.acquisition_form_publications (
 form_key text PRIMARY KEY,
 workspace_id uuid NOT NULL,
 campaign_id uuid NOT NULL,
 form_id uuid NOT NULL,
 enabled boolean NOT NULL DEFAULT false,
 phase_one_approval_ref text,
 phase_two_approval_ref text,
 wording_approval_ref text,
 publication_approval_ref text,
 valid_from timestamptz,
 expires_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 FOREIGN KEY(workspace_id,campaign_id,form_key)
  REFERENCES private.acquisition_form_families(workspace_id,campaign_id,form_key),
 FOREIGN KEY(form_id,workspace_id,campaign_id,form_key)
  REFERENCES public.lead_form_configs(id,workspace_id,campaign_id,acquisition_form_key),
 CHECK(NOT enabled OR (
  phase_one_approval_ref IS NOT NULL AND length(trim(phase_one_approval_ref)) BETWEEN 1 AND 2000
  AND phase_two_approval_ref IS NOT NULL AND length(trim(phase_two_approval_ref)) BETWEEN 1 AND 2000
  AND wording_approval_ref IS NOT NULL AND length(trim(wording_approval_ref)) BETWEEN 1 AND 2000
  AND publication_approval_ref IS NOT NULL AND length(trim(publication_approval_ref)) BETWEEN 1 AND 2000
  AND valid_from IS NOT NULL AND isfinite(valid_from) AND expires_at IS NOT NULL AND isfinite(expires_at)
  AND expires_at>valid_from AND expires_at<=valid_from+interval '90 days'))
);
ALTER TABLE private.acquisition_form_publications ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON private.acquisition_form_publications FROM PUBLIC,anon,authenticated,service_role;

CREATE FUNCTION private.audit_acquisition_form_publication() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Disable form publication instead of deleting it' USING ERRCODE='42501'; END IF;
 IF TG_OP='UPDATE' THEN
  IF ROW(NEW.form_key,NEW.workspace_id,NEW.campaign_id,NEW.created_at)
   IS DISTINCT FROM ROW(OLD.form_key,OLD.workspace_id,OLD.campaign_id,OLD.created_at) THEN
   RAISE EXCEPTION 'Form publication identity is immutable' USING ERRCODE='42501'; END IF;
  IF OLD.enabled AND NEW.form_id IS DISTINCT FROM OLD.form_id THEN
   RAISE EXCEPTION 'Disable publication before selecting another version' USING ERRCODE='42501'; END IF;
  IF NEW.form_id IS DISTINCT FROM OLD.form_id THEN
   NEW.phase_one_approval_ref:=NULL; NEW.phase_two_approval_ref:=NULL;
   NEW.wording_approval_ref:=NULL; NEW.publication_approval_ref:=NULL;
   NEW.valid_from:=NULL; NEW.expires_at:=NULL;
  END IF;
 END IF;
 IF NEW.enabled AND (NEW.expires_at IS NULL OR NEW.expires_at<=clock_timestamp()) THEN
  RAISE EXCEPTION 'Unexpired publication review required' USING ERRCODE='22023'; END IF;
 NEW.updated_at:=clock_timestamp();
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,old_value,new_value,workspace_id)
 VALUES('acquisition_form_publication',NEW.form_key,lower(TG_OP),session_user,
  CASE WHEN TG_OP='UPDATE' THEN to_jsonb(OLD) ELSE NULL END,to_jsonb(NEW),NEW.workspace_id);
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.audit_acquisition_form_publication() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_form_publication_audit BEFORE INSERT OR UPDATE OR DELETE
 ON private.acquisition_form_publications FOR EACH ROW EXECUTE FUNCTION private.audit_acquisition_form_publication();

-- The application service may read display wording only. Configuration remains a
-- separately reviewed privileged operation; no browser or worker can enable it.
CREATE FUNCTION private.read_acquisition_public_form(p_form_key text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE publication private.acquisition_form_publications%ROWTYPE;
 form public.lead_form_configs%ROWTYPE;
BEGIN
 IF auth.jwt()->>'role' IS DISTINCT FROM 'service_role' OR p_form_key IS NULL
  OR p_form_key !~ '^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$' THEN
  RAISE EXCEPTION 'Form unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM private.acquisition_activation WHERE singleton AND enabled FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Form unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO publication FROM private.acquisition_form_publications WHERE form_key=p_form_key;
 IF NOT FOUND THEN RAISE EXCEPTION 'Form unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=publication.workspace_id AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Form unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.ad_campaigns WHERE id=publication.campaign_id AND workspace_id=publication.workspace_id
  AND acquisition_channel='online_offer' AND status='draft' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Form unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO publication FROM private.acquisition_form_publications WHERE form_key=p_form_key FOR SHARE;
 SELECT * INTO form FROM public.lead_form_configs WHERE id=publication.form_id
  AND workspace_id=publication.workspace_id AND campaign_id=publication.campaign_id
  AND acquisition_form_key=p_form_key FOR SHARE;
 IF NOT FOUND OR NOT publication.enabled OR publication.valid_from>clock_timestamp()
  OR publication.expires_at<=clock_timestamp() OR publication.valid_from IS NULL OR publication.expires_at IS NULL
  OR form.active IS DISTINCT FROM false OR form.send_confirmation_sms IS DISTINCT FROM false
  OR form.send_confirmation_email IS DISTINCT FROM false THEN
  RAISE EXCEPTION 'Form unavailable' USING ERRCODE='42501'; END IF;
 RETURN jsonb_build_object('form_key',p_form_key,'version',form.acquisition_form_version,
  'privacy_acknowledged',form.acquisition_form_definition->>'privacy_acknowledged',
  'human_callback_requested',form.acquisition_form_definition->>'human_callback_requested',
  'email_reply_requested',form.acquisition_form_definition->>'email_reply_requested');
END $$;
CREATE FUNCTION public.read_acquisition_public_form(p_form_key text) RETURNS jsonb
LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.read_acquisition_public_form(p_form_key) $$;
REVOKE ALL ON FUNCTION private.read_acquisition_public_form(text),public.read_acquisition_public_form(text)
 FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.read_acquisition_public_form(text),public.read_acquisition_public_form(text) TO service_role;
COMMIT;
