-- Reuse the campaign master. Legacy rows stay unscoped; no provider action.
BEGIN;
ALTER TABLE public.ad_campaigns
 ADD COLUMN workspace_id uuid REFERENCES public.workspaces(id),
 ADD COLUMN acquisition_channel text,
 ADD COLUMN acquisition_budget_cents bigint,
 ADD COLUMN acquisition_currency text,
 ADD COLUMN acquisition_created_by uuid REFERENCES public.profiles(id),
 ADD CONSTRAINT acquisition_campaign_shape CHECK (
  (workspace_id IS NULL AND acquisition_channel IS NULL AND acquisition_budget_cents IS NULL AND acquisition_currency IS NULL AND acquisition_created_by IS NULL)
  OR (workspace_id IS NOT NULL AND acquisition_channel IS NOT NULL AND acquisition_channel IN ('facebook','inbound_voice','direct_mail','online_offer','human_voice','agency_voice')
   AND acquisition_budget_cents IS NOT NULL AND acquisition_budget_cents>=0 AND acquisition_budget_cents<=100000000000
   AND acquisition_currency IS NOT NULL AND acquisition_currency='USD' AND acquisition_created_by IS NOT NULL));
CREATE INDEX acquisition_campaign_workspace_idx ON public.ad_campaigns(workspace_id,id) WHERE workspace_id IS NOT NULL;
ALTER TABLE public.ad_campaigns ENABLE ROW LEVEL SECURITY;
REVOKE TRUNCATE,TRIGGER ON public.ad_campaigns,public.ad_creatives,public.lead_form_configs FROM PUBLIC,anon,authenticated,service_role;
DROP POLICY IF EXISTS acquisition_legacy_boundary ON public.ad_campaigns;
CREATE POLICY acquisition_campaign_read ON public.ad_campaigns AS RESTRICTIVE FOR SELECT TO authenticated
 USING(CASE WHEN workspace_id IS NULL THEN private.acquisition_legacy_access()
 ELSE coalesce(private.acquisition_role(workspace_id) IN ('owner','admin','operator'),false) END);
CREATE POLICY acquisition_campaign_insert ON public.ad_campaigns AS RESTRICTIVE FOR INSERT TO authenticated
 WITH CHECK(workspace_id IS NULL AND private.acquisition_legacy_access());
CREATE POLICY acquisition_campaign_update ON public.ad_campaigns AS RESTRICTIVE FOR UPDATE TO authenticated
 USING(workspace_id IS NULL AND private.acquisition_legacy_access()) WITH CHECK(workspace_id IS NULL AND private.acquisition_legacy_access());
CREATE POLICY acquisition_campaign_delete ON public.ad_campaigns AS RESTRICTIVE FOR DELETE TO authenticated
 USING(workspace_id IS NULL AND private.acquisition_legacy_access());

CREATE FUNCTION private.create_acquisition_campaign(p_id uuid,p_workspace uuid,p_name text,p_channel text,p_budget_cents bigint,p_currency text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.ad_campaigns%ROWTYPE; active boolean; duplicate boolean:=false;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') THEN RAISE EXCEPTION 'Campaign administrator required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_name IS NULL OR length(trim(p_name)) NOT BETWEEN 1 AND 200
  OR p_channel IS NULL OR p_channel NOT IN ('facebook','inbound_voice','direct_mail','online_offer','human_voice','agency_voice')
  OR p_budget_cents IS NULL OR p_budget_cents<0 OR p_budget_cents>100000000000 OR p_currency IS DISTINCT FROM 'USD' THEN
  RAISE EXCEPTION 'Invalid campaign draft inputs' USING ERRCODE='22023'; END IF;
 SELECT enabled INTO active FROM private.acquisition_activation WHERE singleton FOR SHARE;
 IF active IS DISTINCT FROM true THEN RAISE EXCEPTION 'Acquisition activation required' USING ERRCODE='55000'; END IF;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id JOIN auth.sessions s ON s.user_id=p.id
 WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active' AND m.role IN ('owner','admin') AND p.status='approved'
 AND s.id::text=auth.jwt()->>'session_id' AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Campaign authority changed' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-campaign:'||p_id::text,0));
 SELECT * INTO saved FROM public.ad_campaigns WHERE id=p_id;
 IF FOUND THEN
  IF ROW(saved.workspace_id,saved.name,saved.acquisition_channel,saved.acquisition_budget_cents,saved.acquisition_currency,saved.acquisition_created_by)
   IS DISTINCT FROM ROW(p_workspace,trim(p_name),p_channel,p_budget_cents,p_currency,auth.uid()) THEN
   RAISE EXCEPTION 'Campaign request conflict' USING ERRCODE='23505'; END IF;
  duplicate:=true;
 ELSE
  INSERT INTO public.ad_campaigns(id,name,workspace_id,acquisition_channel,acquisition_budget_cents,acquisition_currency,acquisition_created_by,
   platform,status,campaign_objective,daily_budget,total_spend,impressions,clicks,leads_count)
  VALUES(p_id,trim(p_name),p_workspace,p_channel,p_budget_cents,p_currency,auth.uid(),
   CASE WHEN p_channel='facebook' THEN 'facebook' ELSE NULL END,'draft','principal_property_acquisition',NULL,NULL,NULL,NULL,NULL) RETURNING * INTO saved;
  INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
  VALUES('acquisition_campaign',p_id::text,'draft_created',auth.uid()::text,
   jsonb_build_object('channel',p_channel,'budget_cents',p_budget_cents,'currency',p_currency,'status','draft'),p_workspace);
 END IF;
 RETURN jsonb_build_object('id',saved.id,'workspace_id',saved.workspace_id,'status',saved.status,'channel',saved.acquisition_channel,
  'budget_cents',saved.acquisition_budget_cents,'currency',saved.acquisition_currency,'duplicate',duplicate,'execution_authorized',false);
END $$;
CREATE FUNCTION public.create_acquisition_campaign(p_id uuid,p_workspace uuid,p_name text,p_channel text,p_budget_cents bigint,p_currency text)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.create_acquisition_campaign(p_id,p_workspace,p_name,p_channel,p_budget_cents,p_currency) $$;
REVOKE ALL ON FUNCTION private.create_acquisition_campaign(uuid,uuid,text,text,bigint,text),public.create_acquisition_campaign(uuid,uuid,text,text,bigint,text) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.create_acquisition_campaign(uuid,uuid,text,text,bigint,text),public.create_acquisition_campaign(uuid,uuid,text,text,bigint,text) TO authenticated;

CREATE FUNCTION private.protect_acquisition_campaign() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE scoped boolean; function_owner text;
BEGIN
 scoped:=CASE WHEN TG_OP='DELETE' THEN OLD.workspace_id IS NOT NULL ELSE NEW.workspace_id IS NOT NULL END;
 IF TG_OP='UPDATE' THEN scoped:=scoped OR OLD.workspace_id IS NOT NULL; END IF;
 IF NOT scoped THEN RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END; END IF;
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Campaign drafts require controlled versioned changes' USING ERRCODE='42501'; END IF;
 SELECT pg_get_userbyid(proowner) INTO function_owner FROM pg_proc WHERE oid='private.create_acquisition_campaign(uuid,uuid,text,text,bigint,text)'::regprocedure;
 IF current_user<>function_owner THEN RAISE EXCEPTION 'Use acquisition campaign functions' USING ERRCODE='42501'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_acquisition_campaign() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER protect_acquisition_campaign BEFORE INSERT OR UPDATE OR DELETE ON public.ad_campaigns
 FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_campaign();

-- Until reviewed child enrollment exists, no legacy writer (including definer
-- finalization RPCs) may associate a public form, creative or lead to this scope.
CREATE FUNCTION private.reject_acquisition_campaign_association() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE parent uuid; parents uuid[]; scope uuid;
BEGIN
 parents:=ARRAY[(to_jsonb(NEW)->>TG_ARGV[0])::uuid];
 IF TG_OP='UPDATE' THEN parents:=parents||ARRAY[(to_jsonb(OLD)->>TG_ARGV[0])::uuid]; END IF;
 FOREACH parent IN ARRAY parents LOOP
  IF parent IS NULL THEN CONTINUE; END IF;
  SELECT workspace_id INTO scope FROM public.ad_campaigns WHERE id=parent FOR SHARE;
  -- Require a visible committed parent rather than relying on a later FK wait
  -- that could otherwise observe a concurrently created scoped campaign.
  IF NOT FOUND THEN RAISE EXCEPTION 'Campaign parent unavailable' USING ERRCODE='23503'; END IF;
  IF scope IS NOT NULL THEN RAISE EXCEPTION 'Reviewed acquisition campaign association required' USING ERRCODE='42501'; END IF;
 END LOOP;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.reject_acquisition_campaign_association() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER acquisition_creative_campaign_guard BEFORE INSERT OR UPDATE ON public.ad_creatives
 FOR EACH ROW EXECUTE FUNCTION private.reject_acquisition_campaign_association('campaign_id');
CREATE TRIGGER acquisition_form_campaign_guard BEFORE INSERT OR UPDATE ON public.lead_form_configs
 FOR EACH ROW EXECUTE FUNCTION private.reject_acquisition_campaign_association('campaign_id');
CREATE TRIGGER acquisition_lead_campaign_guard BEFORE INSERT OR UPDATE ON public.leads
 FOR EACH ROW EXECUTE FUNCTION private.reject_acquisition_campaign_association('ad_campaign_id');
COMMIT;
