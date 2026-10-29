-- One read snapshot for a current content review and enrolled canonical property.
BEGIN;
CREATE FUNCTION private.acquisition_mail_proof_context(p_workspace uuid,p_campaign uuid,p_content uuid,p_lead uuid)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE review_state jsonb; property_row wholesale_ingest.properties%ROWTYPE;
BEGIN
 -- Authorize before disclosing either review or property information.
 review_state:=private.acquisition_mail_content_state(p_workspace,p_campaign,p_content);
 IF (review_state->>'review_current')::boolean IS DISTINCT FROM true THEN
  RAISE EXCEPTION 'Current content approval required for proof' USING ERRCODE='55000'; END IF;
 SELECT p.* INTO property_row FROM public.workspace_leads b JOIN wholesale_ingest.properties p
  ON p.id=b.property_id AND p.lead_id=b.lead_id
 WHERE b.workspace_id=p_workspace AND b.lead_id=p_lead;
 IF NOT FOUND THEN RAISE EXCEPTION 'Enrolled canonical property unavailable' USING ERRCODE='42501'; END IF;
 IF nullif(trim(property_row.address_std),'') IS NULL OR nullif(trim(property_row.city),'') IS NULL
  OR nullif(trim(property_row.state),'') IS NULL THEN
  RAISE EXCEPTION 'Complete canonical property address required' USING ERRCODE='55000'; END IF;
 RETURN jsonb_build_object('workspace_id',p_workspace,'campaign_id',p_campaign,'content_id',p_content,'lead_id',p_lead,
  'property',jsonb_build_object('property_id',property_row.id,'lead_id',property_row.lead_id,
   'address_std',property_row.address_std,'unit',property_row.unit,'city',property_row.city,'state',property_row.state,'zip',property_row.zip),
  'review_state',review_state,'checked_at',statement_timestamp(),'execution_authorized',false);
END $$;
CREATE FUNCTION public.acquisition_mail_proof_context(p_workspace uuid,p_campaign uuid,p_content uuid,p_lead uuid)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$
 SELECT private.acquisition_mail_proof_context(p_workspace,p_campaign,p_content,p_lead)
$$;
REVOKE ALL ON FUNCTION private.acquisition_mail_proof_context(uuid,uuid,uuid,uuid),public.acquisition_mail_proof_context(uuid,uuid,uuid,uuid)
 FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_mail_proof_context(uuid,uuid,uuid,uuid),public.acquisition_mail_proof_context(uuid,uuid,uuid,uuid) TO authenticated;
COMMIT;
