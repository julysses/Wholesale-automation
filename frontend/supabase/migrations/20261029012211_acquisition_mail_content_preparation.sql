-- Read-only content preparation; approval persistence and fulfillment remain separate.
BEGIN;
CREATE FUNCTION private.prepare_acquisition_mail_content(p_workspace uuid,p_campaign uuid,p_creative uuid,p_destination_review uuid,p_company_name text)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE creative public.ad_creatives%ROWTYPE; destination public.acquisition_mail_destination_reviews%ROWTYPE;
 destination_state jsonb; snapshot jsonb; preparation_hash text;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Mail content access denied' USING ERRCODE='42501'; END IF;
 IF p_company_name IS NULL OR length(trim(p_company_name)) NOT BETWEEN 1 AND 200
  OR p_company_name ~ '[[:cntrl:]{}]' THEN
  RAISE EXCEPTION 'Proposed company identity required' USING ERRCODE='22023'; END IF;
 IF NOT EXISTS(SELECT 1 FROM private.acquisition_activation WHERE singleton AND enabled)
  OR NOT EXISTS(SELECT 1 FROM public.workspaces WHERE id=p_workspace AND status='active') THEN
  RAISE EXCEPTION 'Acquisition preparation unavailable' USING ERRCODE='55000'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.ad_campaigns WHERE id=p_campaign AND workspace_id=p_workspace
  AND acquisition_channel='direct_mail' AND status='draft') THEN
  RAISE EXCEPTION 'Mail campaign unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO creative FROM public.ad_creatives WHERE id=p_creative AND workspace_id=p_workspace AND campaign_id=p_campaign;
 IF NOT FOUND OR creative.acquisition_template_id IS NULL THEN
  RAISE EXCEPTION 'Mail template unavailable' USING ERRCODE='42501'; END IF;
 IF EXISTS(SELECT 1 FROM public.ad_creatives WHERE workspace_id=p_workspace
  AND acquisition_template_id=creative.acquisition_template_id AND acquisition_template_version>creative.acquisition_template_version) THEN
  RAISE EXCEPTION 'Mail template version changed' USING ERRCODE='40001'; END IF;
 SELECT * INTO destination FROM public.acquisition_mail_destination_reviews
  WHERE id=p_destination_review AND workspace_id=p_workspace AND campaign_id=p_campaign;
 IF NOT FOUND THEN RAISE EXCEPTION 'Mail destination unavailable' USING ERRCODE='42501'; END IF;
 destination_state:=private.acquisition_mail_destination_state(p_workspace,p_campaign,destination.destination_id);
 IF (destination_state->>'review_current')::boolean IS DISTINCT FROM true
  OR destination_state->'latest_review'->>'id' IS DISTINCT FROM p_destination_review::text THEN
  RAISE EXCEPTION 'Current destination review required' USING ERRCODE='55000'; END IF;
 IF creative.acquisition_tracking_mode IS DISTINCT FROM destination.mode THEN
  RAISE EXCEPTION 'Message and destination response methods differ' USING ERRCODE='22023'; END IF;
 -- This digest is deliberately distinct from the Python renderer content_binding.
 -- Excludes check time; includes immutable source identities and all routing evidence.
 snapshot:=jsonb_build_object('workspace_id',p_workspace,'campaign_id',p_campaign,
  'renderer_version','acquisition-mail-render-v1','company_name',p_company_name,
  'template',jsonb_build_object('creative_id',creative.id,'template_id',creative.acquisition_template_id,
   'version',creative.acquisition_template_version,'format',creative.acquisition_mail_format,
   'tracking_mode',creative.acquisition_tracking_mode,'body',creative.primary_text),
  'destination',jsonb_build_object('review_id',destination.id,'destination_id',destination.destination_id,
   'version',destination.version,'mode',destination.mode,'value',destination.value,
   'verification_ref',destination.verification_ref,'verification_hash',destination.verification_hash,
   'verified_epoch',extract(epoch from destination.verified_at),'expires_epoch',extract(epoch from destination.expires_at),
   'reviewer_id',destination.actor_id,'reviewer_membership_epoch',extract(epoch from destination.actor_membership_updated_at)));
 preparation_hash:=encode(sha256(convert_to(snapshot::text,'UTF8')),'hex');
 RETURN jsonb_build_object('status','content_prepared','execution_authorized',false,'content_approved',false,
  'snapshot',snapshot,'preparation_hash',preparation_hash,'checked_at',statement_timestamp(),
  'destination_valid_until',destination.expires_at);
END $$;
CREATE FUNCTION public.prepare_acquisition_mail_content(p_workspace uuid,p_campaign uuid,p_creative uuid,p_destination_review uuid,p_company_name text)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.prepare_acquisition_mail_content(p_workspace,p_campaign,p_creative,p_destination_review,p_company_name)
$$;
REVOKE ALL ON FUNCTION private.prepare_acquisition_mail_content(uuid,uuid,uuid,uuid,text),public.prepare_acquisition_mail_content(uuid,uuid,uuid,uuid,text)
 FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.prepare_acquisition_mail_content(uuid,uuid,uuid,uuid,text),public.prepare_acquisition_mail_content(uuid,uuid,uuid,uuid,text) TO authenticated;
COMMIT;
