-- Preserve original touches and exact reviewed campaign attribution separately.
BEGIN;
CREATE TABLE public.acquisition_lead_sources (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 lead_id uuid NOT NULL,
 receipt_id uuid NOT NULL UNIQUE,
 integration_id uuid NOT NULL,
 source_type text NOT NULL CHECK(source_type='facebook_native_form'),
 preparation_hash text NOT NULL,
 external_lead_id text NOT NULL,
 form_id text,
 external_campaign_id text,
 adset_id text,
 ad_id text,
 submitted_at_raw text,
 utm_data jsonb,
 projection_version text NOT NULL DEFAULT 'source-touch-v1' CHECK(projection_version='source-touch-v1'),
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(workspace_id,id),
 FOREIGN KEY(workspace_id,id) REFERENCES public.seller_intakes(workspace_id,id),
 FOREIGN KEY(workspace_id,lead_id) REFERENCES public.workspace_leads(workspace_id,lead_id),
 FOREIGN KEY(receipt_id,workspace_id) REFERENCES public.webhook_jobs(id,workspace_id),
 FOREIGN KEY(integration_id,workspace_id) REFERENCES private.acquisition_integrations(id,workspace_id)
);
CREATE INDEX acquisition_lead_sources_lead ON public.acquisition_lead_sources(workspace_id,lead_id,id);
CREATE INDEX acquisition_lead_sources_campaign ON public.acquisition_lead_sources(integration_id,external_campaign_id,id);
ALTER TABLE public.acquisition_lead_sources ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_lead_sources FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_lead_sources TO authenticated;
CREATE POLICY acquisition_lead_sources_read ON public.acquisition_lead_sources FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE TRIGGER acquisition_lead_sources_immutable BEFORE UPDATE OR DELETE ON public.acquisition_lead_sources
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

CREATE FUNCTION private.acquisition_source_identifier(p_data jsonb,p_key text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT CASE WHEN jsonb_typeof(p_data->p_key)='string' AND p_data->>p_key ~ '^[0-9]{1,200}$' THEN p_data->>p_key ELSE NULL END
$$;
REVOKE ALL ON FUNCTION private.acquisition_source_identifier(jsonb,text) FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION private.record_acquisition_lead_source(p_intake uuid) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE intake public.seller_intakes%ROWTYPE; receipt public.webhook_jobs%ROWTYPE; evidence jsonb;
BEGIN
 SELECT * INTO intake FROM public.seller_intakes WHERE id=p_intake;
 IF NOT FOUND THEN RAISE EXCEPTION 'Source intake unavailable'; END IF;
 SELECT * INTO receipt FROM public.webhook_jobs WHERE id=intake.receipt_id AND workspace_id=intake.workspace_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'Source receipt unavailable'; END IF;
 evidence:=intake.prepared_answers->'provider_evidence';
 INSERT INTO public.acquisition_lead_sources(id,workspace_id,lead_id,receipt_id,integration_id,source_type,preparation_hash,external_lead_id,
  form_id,external_campaign_id,adset_id,ad_id,submitted_at_raw,utm_data)
 VALUES(intake.id,intake.workspace_id,intake.lead_id,intake.receipt_id,receipt.acquisition_integration_id,intake.source_type,intake.preparation_hash,receipt.external_event_id,
  private.acquisition_source_identifier(evidence,'form_id'),private.acquisition_source_identifier(evidence,'campaign_id'),
  private.acquisition_source_identifier(evidence,'adset_id'),private.acquisition_source_identifier(evidence,'ad_id'),
  CASE WHEN jsonb_typeof(evidence->'created_time')='string' AND length(evidence->>'created_time')<=200 THEN evidence->>'created_time' ELSE NULL END,NULL)
 ON CONFLICT(id) DO NOTHING;
 IF FOUND THEN
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('acquisition_lead_source',intake.id::text,'source_recorded','intake_ingestion',
   jsonb_build_object('receipt_id',receipt.id,'lead_id',intake.lead_id,'projection_version','source-touch-v1','preparation_hash',intake.preparation_hash),intake.workspace_id);
 END IF;
END $$;
REVOKE ALL ON FUNCTION private.record_acquisition_lead_source(uuid) FROM PUBLIC,anon,authenticated,service_role;
CREATE FUNCTION private.record_acquisition_lead_source_trigger() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN PERFORM private.record_acquisition_lead_source(NEW.id); RETURN NEW; END $$;
REVOKE ALL ON FUNCTION private.record_acquisition_lead_source_trigger() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_intake_source AFTER INSERT ON public.seller_intakes
 FOR EACH ROW EXECUTE FUNCTION private.record_acquisition_lead_source_trigger();
-- Existing immutable inquiry evidence receives the same projection; no new leads.
DO $$ DECLARE row record; BEGIN
 FOR row IN SELECT id FROM public.seller_intakes ORDER BY id LOOP PERFORM private.record_acquisition_lead_source(row.id); END LOOP;
END $$;

ALTER TABLE public.acquisition_campaign_links ADD CONSTRAINT acquisition_campaign_link_workspace_unique UNIQUE(workspace_id,id);
CREATE TABLE public.acquisition_source_campaign_reviews (
 id uuid PRIMARY KEY,
 workspace_id uuid NOT NULL,
 source_id uuid NOT NULL,
 link_review_id uuid NOT NULL,
 campaign_id uuid NOT NULL,
 preparation_hash text NOT NULL,
 actor_id uuid NOT NULL REFERENCES public.profiles(id),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(source_id,link_review_id),
 FOREIGN KEY(workspace_id,source_id) REFERENCES public.acquisition_lead_sources(workspace_id,id),
 FOREIGN KEY(workspace_id,link_review_id) REFERENCES public.acquisition_campaign_links(workspace_id,id),
 FOREIGN KEY(workspace_id,campaign_id) REFERENCES public.ad_campaigns(workspace_id,id)
);
CREATE INDEX acquisition_source_campaign_reviews_scope ON public.acquisition_source_campaign_reviews(workspace_id,source_id,created_at,id);
ALTER TABLE public.acquisition_source_campaign_reviews ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.acquisition_source_campaign_reviews FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON public.acquisition_source_campaign_reviews TO authenticated;
CREATE POLICY acquisition_source_campaign_reviews_read ON public.acquisition_source_campaign_reviews FOR SELECT TO authenticated
 USING(private.acquisition_role(workspace_id) IN ('owner','admin','operator'));
CREATE TRIGGER acquisition_source_campaign_reviews_immutable BEFORE UPDATE OR DELETE ON public.acquisition_source_campaign_reviews
 FOR EACH ROW EXECUTE FUNCTION private.preserve_acquisition_contact();

CREATE FUNCTION private.capture_acquisition_source_campaign(p_id uuid,p_workspace uuid,p_source uuid,p_link_review uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE source public.acquisition_lead_sources%ROWTYPE; review public.acquisition_campaign_links%ROWTYPE;
 saved public.acquisition_source_campaign_reviews%ROWTYPE; state jsonb;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN RAISE EXCEPTION 'Workspace attribution access required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_link_review IS NULL THEN RAISE EXCEPTION 'Exact source review required' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM private.acquisition_activation WHERE singleton FOR SHARE;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id JOIN auth.sessions s ON s.user_id=p.id
 WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active' AND m.role IN ('owner','admin','operator') AND p.status='approved'
 AND s.id::text=auth.jwt()->>'session_id' AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Attribution authority changed' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('source-campaign-request:'||p_id::text,0));
 SELECT * INTO source FROM public.acquisition_lead_sources WHERE workspace_id=p_workspace AND id=p_source FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Source unavailable' USING ERRCODE='42501'; END IF;
 SELECT * INTO saved FROM public.acquisition_source_campaign_reviews WHERE id=p_id;
 IF FOUND THEN
  IF ROW(saved.workspace_id,saved.source_id,saved.link_review_id,saved.actor_id) IS DISTINCT FROM ROW(p_workspace,p_source,p_link_review,auth.uid()) THEN
   RAISE EXCEPTION 'Source attribution request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('id',saved.id,'source_id',saved.source_id,'link_review_id',saved.link_review_id,'campaign_id',saved.campaign_id,'duplicate',true,'execution_authorized',false);
 END IF;
 -- Same lock as campaign review/revocation prevents a stale capture at commit.
 PERFORM pg_advisory_xact_lock(hashtextextended('facebook-campaign-link:'||source.external_campaign_id,0));
 SELECT * INTO review FROM public.acquisition_campaign_links WHERE id=p_link_review AND workspace_id=p_workspace;
 IF NOT FOUND OR review.action<>'link' OR ROW(review.integration_id,review.external_campaign_id) IS DISTINCT FROM ROW(source.integration_id,source.external_campaign_id) THEN
  RAISE EXCEPTION 'Source campaign identity mismatch' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM private.acquisition_integrations WHERE id=source.integration_id FOR SHARE;
 PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id WHERE m.workspace_id=p_workspace AND m.user_id=review.actor_id FOR SHARE OF m,p;
 PERFORM 1 FROM public.ad_campaigns WHERE id=review.campaign_id AND workspace_id=p_workspace FOR SHARE;
 state:=private.acquisition_campaign_link_state(p_workspace,p_source);
 IF state->'link_current' IS DISTINCT FROM 'true'::jsonb OR state->'latest_review'->>'id' IS DISTINCT FROM p_link_review::text THEN
  RAISE EXCEPTION 'Current reviewed campaign required' USING ERRCODE='40001'; END IF;
 INSERT INTO public.acquisition_source_campaign_reviews(id,workspace_id,source_id,link_review_id,campaign_id,preparation_hash,actor_id)
 VALUES(p_id,p_workspace,p_source,p_link_review,review.campaign_id,source.preparation_hash,auth.uid());
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_source_campaign',p_id::text,'attribution_captured',auth.uid()::text,
  jsonb_build_object('source_id',p_source,'link_review_id',p_link_review,'campaign_id',review.campaign_id,'execution_authorized',false),p_workspace);
 RETURN jsonb_build_object('id',p_id,'source_id',p_source,'link_review_id',p_link_review,'campaign_id',review.campaign_id,'duplicate',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.capture_acquisition_source_campaign(p_id uuid,p_workspace uuid,p_source uuid,p_link_review uuid)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.capture_acquisition_source_campaign(p_id,p_workspace,p_source,p_link_review) $$;
REVOKE ALL ON FUNCTION private.capture_acquisition_source_campaign(uuid,uuid,uuid,uuid),public.capture_acquisition_source_campaign(uuid,uuid,uuid,uuid) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.capture_acquisition_source_campaign(uuid,uuid,uuid,uuid),public.capture_acquisition_source_campaign(uuid,uuid,uuid,uuid) TO authenticated;
COMMIT;
