-- Audited, idempotent, compare-and-set Facebook attribution reconciliation.
-- Fills ONLY null ad_campaign_id/ad_creative_id on an existing native Facebook
-- lead after exact Meta receipt identity is proven. Never overwrites existing
-- attribution, never creates campaigns/creatives, never queues or sends outreach.
-- NOT APPLIED TO PRODUCTION. Requires explicit owner authorization to release.
CREATE FUNCTION public.reconcile_facebook_lead_attribution(
  p_lead_id uuid,
  p_leadgen_id text,
  p_campaign_id uuid,
  p_creative_id uuid,
  p_actor text,
  p_reason text
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE
  v_lead public.leads%ROWTYPE;
  v_patch jsonb := '{}'::jsonb;
  v_old jsonb;
BEGIN
  IF p_lead_id IS NULL OR coalesce(p_leadgen_id,'')='' OR p_campaign_id IS NULL
     OR coalesce(p_actor,'')='' OR coalesce(p_reason,'')='' THEN
    RAISE EXCEPTION 'Lead, Meta lead, campaign, actor and reason are required';
  END IF;

  SELECT * INTO v_lead FROM public.leads WHERE id=p_lead_id FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Lead not found'; END IF;
  IF v_lead.source IS DISTINCT FROM 'facebook_lead_ad' THEN
    RAISE EXCEPTION 'Not a Facebook inquiry';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.facebook_lead_submissions s
                 WHERE s.lead_id=p_lead_id AND s.leadgen_id=p_leadgen_id) THEN
    RAISE EXCEPTION 'Meta lead identity does not match this lead';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM public.ad_campaigns c
                 WHERE c.id=p_campaign_id AND c.platform='facebook') THEN
    RAISE EXCEPTION 'Campaign is not a registered Facebook campaign';
  END IF;
  IF p_creative_id IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM public.ad_creatives a
       WHERE a.id=p_creative_id AND a.campaign_id=p_campaign_id) THEN
    RAISE EXCEPTION 'Creative does not belong to campaign';
  END IF;

  IF v_lead.ad_campaign_id IS NOT NULL AND v_lead.ad_campaign_id<>p_campaign_id THEN
    RAISE EXCEPTION 'Existing attribution conflicts';
  END IF;
  IF p_creative_id IS NOT NULL AND v_lead.ad_creative_id IS NOT NULL
     AND v_lead.ad_creative_id<>p_creative_id THEN
    RAISE EXCEPTION 'Existing attribution conflicts';
  END IF;

  IF v_lead.ad_campaign_id IS NULL THEN
    v_patch := v_patch || jsonb_build_object('ad_campaign_id',p_campaign_id);
  END IF;
  IF p_creative_id IS NOT NULL AND v_lead.ad_creative_id IS NULL THEN
    v_patch := v_patch || jsonb_build_object('ad_creative_id',p_creative_id);
  END IF;

  IF v_patch='{}'::jsonb THEN
    RETURN jsonb_build_object('applied',false,'lead_id',p_lead_id,'patch',v_patch);
  END IF;

  v_old := jsonb_build_object('ad_campaign_id',v_lead.ad_campaign_id,
                              'ad_creative_id',v_lead.ad_creative_id);
  UPDATE public.leads SET
    ad_campaign_id=coalesce(ad_campaign_id,p_campaign_id),
    ad_creative_id=coalesce(ad_creative_id,p_creative_id)
  WHERE id=p_lead_id;

  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,old_value,new_value,metadata)
  VALUES('lead',p_lead_id::text,'facebook_attribution_reconciled',p_actor,v_old,v_patch,
         jsonb_build_object('leadgen_id',p_leadgen_id,'reason',p_reason));

  RETURN jsonb_build_object('applied',true,'lead_id',p_lead_id,'patch',v_patch);
END $$;
REVOKE ALL ON FUNCTION public.reconcile_facebook_lead_attribution(uuid,text,uuid,uuid,text,text)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.reconcile_facebook_lead_attribution(uuid,text,uuid,uuid,text,text)
  TO service_role;
