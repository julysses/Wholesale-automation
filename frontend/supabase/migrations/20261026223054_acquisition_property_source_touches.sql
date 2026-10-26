-- Read-only canonical-property source reporting; no record merging or totals.
BEGIN;
CREATE INDEX acquisition_identity_reviews_target_sources
 ON public.acquisition_intake_identity_reviews(workspace_id,target_lead_id,intake_id)
 WHERE target_lead_id IS NOT NULL;
CREATE FUNCTION private.acquisition_property_source_touches(p_workspace uuid,p_lead uuid,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE source public.acquisition_lead_sources%ROWTYPE; property uuid; identity_state jsonb; campaign_state jsonb;
 snapshot public.acquisition_source_campaign_reviews%ROWTYPE; items jsonb:='[]'::jsonb;
 scanned integer:=0; excluded integer:=0; last_scanned uuid; more boolean:=false;
 association text; identity_review uuid; current_attribution boolean; attribution_status text;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN
  RAISE EXCEPTION 'Workspace property reporting access required' USING ERRCODE='42501'; END IF;
 IF p_limit IS NULL OR p_limit<1 OR p_limit>50 THEN RAISE EXCEPTION 'Invalid source page size' USING ERRCODE='22023'; END IF;
 SELECT b.property_id INTO property FROM public.workspace_leads b JOIN wholesale_ingest.properties p ON p.id=b.property_id AND p.lead_id=b.lead_id
 WHERE b.workspace_id=p_workspace AND b.lead_id=p_lead;
 IF NOT FOUND THEN RAISE EXCEPTION 'Canonical workspace property unavailable' USING ERRCODE='42501'; END IF;
 -- Historical target references locate candidates; current review evaluation is
 -- decisive. Bound candidate pages prevent unlimited per-source policy calls.
 FOR source IN
  WITH candidates AS (
   (SELECT id FROM public.acquisition_lead_sources WHERE workspace_id=p_workspace AND lead_id=p_lead AND (p_after IS NULL OR id>p_after) ORDER BY id LIMIT p_limit+1)
   UNION
   (SELECT DISTINCT intake_id FROM public.acquisition_intake_identity_reviews WHERE workspace_id=p_workspace AND target_lead_id=p_lead AND (p_after IS NULL OR intake_id>p_after) ORDER BY intake_id LIMIT p_limit+1)
  ) SELECT s.* FROM public.acquisition_lead_sources s JOIN candidates c ON c.id=s.id
    WHERE s.workspace_id=p_workspace ORDER BY s.id LIMIT p_limit+1
 LOOP
  IF scanned=p_limit THEN more:=true; EXIT; END IF;
  scanned:=scanned+1; last_scanned:=source.id; identity_review:=NULL; association:='original_lead';
  IF source.lead_id<>p_lead THEN
   identity_state:=private.acquisition_intake_identity_state(p_workspace,source.id,NULL);
   IF identity_state->'link_current' IS DISTINCT FROM 'true'::jsonb
    OR identity_state->'latest_review'->>'target_lead_id' IS DISTINCT FROM p_lead::text
    OR identity_state->'latest_review'->>'target_property_id' IS DISTINCT FROM property::text THEN
    excluded:=excluded+1; CONTINUE; END IF;
   identity_review:=(identity_state->'latest_review'->>'id')::uuid;
   association:=CASE identity_state->'latest_review'->>'action' WHEN 'repeat_inquiry' THEN 'reviewed_repeat_inquiry' ELSE 'reviewed_property' END;
  END IF;
  campaign_state:=NULL; snapshot:=NULL; current_attribution:=false; attribution_status:='campaign_evidence_unavailable';
  IF source.external_campaign_id IS NOT NULL THEN
   BEGIN campaign_state:=private.acquisition_campaign_link_state(p_workspace,source.id);
   EXCEPTION WHEN SQLSTATE '55000' THEN campaign_state:=NULL;
   END;
  END IF;
  IF campaign_state IS NOT NULL THEN
   attribution_status:='campaign_review_not_current';
   IF campaign_state->'link_current'='true'::jsonb THEN
    SELECT * INTO snapshot FROM public.acquisition_source_campaign_reviews
     WHERE workspace_id=p_workspace AND source_id=source.id AND link_review_id=(campaign_state->'latest_review'->>'id')::uuid;
    current_attribution:=FOUND;
    attribution_status:=CASE WHEN current_attribution THEN 'current_captured_attribution' ELSE 'current_review_not_captured' END;
   END IF;
  END IF;
  IF NOT current_attribution THEN
   SELECT * INTO snapshot FROM public.acquisition_source_campaign_reviews
    WHERE workspace_id=p_workspace AND source_id=source.id ORDER BY created_at DESC,id DESC LIMIT 1;
  END IF;
  items:=items||jsonb_build_array(jsonb_build_object(
   'source_id',source.id,'original_lead_id',source.lead_id,'receipt_id',source.receipt_id,'integration_id',source.integration_id,
   'source_type',source.source_type,'preparation_hash',source.preparation_hash,'external_lead_id',source.external_lead_id,
   'form_id',source.form_id,'external_campaign_id',source.external_campaign_id,'adset_id',source.adset_id,'ad_id',source.ad_id,
   'submitted_at_raw',source.submitted_at_raw,'utm_data',source.utm_data,'association',association,'identity_review_id',identity_review,
   'attribution_status',attribution_status,'attribution_current',current_attribution,
   'current_campaign_id',CASE WHEN current_attribution THEN snapshot.campaign_id ELSE NULL END,
   'captured_attribution',CASE WHEN snapshot.id IS NULL THEN NULL ELSE jsonb_build_object('id',snapshot.id,'link_review_id',snapshot.link_review_id,
      'campaign_id',snapshot.campaign_id,'created_at',snapshot.created_at) END));
 END LOOP;
 RETURN jsonb_build_object('workspace_id',p_workspace,'canonical_lead_id',p_lead,'property_id',property,
  'items',items,'next_after',CASE WHEN more THEN last_scanned ELSE NULL END,'scanned_count',scanned,'excluded_count',excluded,
  'count_scope','bounded_candidate_page','totals_available',false,'checked_at',statement_timestamp(),
  'ownership_verified',false,'contact_permission_granted',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.acquisition_property_source_touches(p_workspace uuid,p_lead uuid,p_after uuid DEFAULT NULL,p_limit integer DEFAULT 20)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_property_source_touches(p_workspace,p_lead,p_after,p_limit) $$;
REVOKE ALL ON FUNCTION private.acquisition_property_source_touches(uuid,uuid,uuid,integer),public.acquisition_property_source_touches(uuid,uuid,uuid,integer) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_property_source_touches(uuid,uuid,uuid,integer),public.acquisition_property_source_touches(uuid,uuid,uuid,integer) TO authenticated;
COMMIT;
