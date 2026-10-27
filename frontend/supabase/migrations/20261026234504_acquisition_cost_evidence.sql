-- Extend the existing performance relation; retain all legacy rows unchanged.
BEGIN;
ALTER TABLE public.fb_campaign_performance
 ADD COLUMN workspace_id uuid,
 ADD COLUMN acquisition_campaign_id uuid,
 ADD COLUMN acquisition_link_review_id uuid,
 ADD COLUMN acquisition_revision integer,
 ADD COLUMN acquisition_amount_minor bigint,
 ADD COLUMN acquisition_coverage text,
 ADD COLUMN acquisition_timezone text,
 ADD COLUMN acquisition_observed_at timestamptz,
 ADD COLUMN acquisition_data jsonb,
 ADD COLUMN acquisition_actor_id uuid REFERENCES public.profiles(id),
 ADD COLUMN acquisition_recorded_at timestamptz,
 ADD CONSTRAINT acquisition_cost_campaign_fk FOREIGN KEY(workspace_id,acquisition_campaign_id) REFERENCES public.ad_campaigns(workspace_id,id),
 ADD CONSTRAINT acquisition_cost_review_fk FOREIGN KEY(workspace_id,acquisition_link_review_id) REFERENCES public.acquisition_campaign_links(workspace_id,id),
 ADD CONSTRAINT acquisition_cost_shape CHECK (
  (workspace_id IS NULL AND acquisition_campaign_id IS NULL AND acquisition_link_review_id IS NULL AND acquisition_revision IS NULL
   AND acquisition_amount_minor IS NULL AND acquisition_coverage IS NULL AND acquisition_timezone IS NULL AND acquisition_observed_at IS NULL
   AND acquisition_data IS NULL AND acquisition_actor_id IS NULL AND acquisition_recorded_at IS NULL)
  OR (workspace_id IS NOT NULL AND acquisition_campaign_id IS NOT NULL AND acquisition_link_review_id IS NOT NULL
   AND acquisition_revision IS NOT NULL AND acquisition_revision>0 AND acquisition_coverage IS NOT NULL AND acquisition_coverage IN ('complete','partial','withdrawn')
   AND ((acquisition_coverage='withdrawn' AND acquisition_amount_minor IS NULL) OR (acquisition_coverage<>'withdrawn' AND acquisition_amount_minor IS NOT NULL AND acquisition_amount_minor BETWEEN 0 AND 100000000000000))
   AND acquisition_timezone IS NOT NULL AND acquisition_observed_at IS NOT NULL AND isfinite(acquisition_observed_at)
   AND acquisition_data IS NOT NULL AND jsonb_typeof(acquisition_data)='object' AND acquisition_actor_id IS NOT NULL AND acquisition_recorded_at IS NOT NULL
   AND campaign_id IS NULL AND ad_set_id IS NULL AND spend IS NULL AND leads IS NULL AND contact_rate IS NULL AND appt_rate IS NULL AND frequency IS NULL AND isfinite(date)));
CREATE UNIQUE INDEX acquisition_cost_day_revision ON public.fb_campaign_performance(workspace_id,acquisition_campaign_id,date,acquisition_revision) WHERE workspace_id IS NOT NULL;
CREATE INDEX acquisition_cost_review ON public.fb_campaign_performance(acquisition_link_review_id) WHERE workspace_id IS NOT NULL;
ALTER TABLE public.fb_campaign_performance ENABLE ROW LEVEL SECURITY;
REVOKE TRUNCATE,TRIGGER ON public.fb_campaign_performance FROM PUBLIC,anon,authenticated,service_role;
-- Legacy command-center direct queries never include acquisition evidence.
-- Scoped read/write RPCs below supply the separate acquisition boundary.
CREATE POLICY acquisition_cost_namespace ON public.fb_campaign_performance AS RESTRICTIVE FOR ALL TO authenticated
 USING(workspace_id IS NULL AND private.acquisition_legacy_access()) WITH CHECK(workspace_id IS NULL AND private.acquisition_legacy_access());

CREATE FUNCTION private.record_acquisition_cost(p_id uuid,p_workspace uuid,p_link_review uuid,p_data jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE saved public.fb_campaign_performance%ROWTYPE; review public.acquisition_campaign_links%ROWTYPE;
 state jsonb; day date; observed timestamptz; amount bigint; coverage text; zone text; expected integer; seq integer;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin') OR auth.jwt()->>'aal' IS DISTINCT FROM 'aal2' THEN
  RAISE EXCEPTION 'Cost review administrator and MFA required' USING ERRCODE='42501'; END IF;
 IF p_id IS NULL OR p_link_review IS NULL OR p_data IS NULL OR jsonb_typeof(p_data)<>'object' THEN
  RAISE EXCEPTION 'Exact cost evidence required' USING ERRCODE='22023'; END IF;
 IF (SELECT count(*) FROM jsonb_object_keys(p_data))<>11 OR NOT p_data ?& ARRAY['date','amount_minor','coverage','currency','reporting_timezone','observed_at','external_campaign_id','ad_account_id','evidence_ref','evidence_hash','expected_revision']
 OR jsonb_typeof(p_data->'date') IS DISTINCT FROM 'string' OR p_data->>'date' !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
 OR jsonb_typeof(p_data->'observed_at') IS DISTINCT FROM 'string' OR p_data->>'observed_at' !~ 'T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?(Z|[+-][0-9]{2}:[0-9]{2})$'
 OR jsonb_typeof(p_data->'reporting_timezone') IS DISTINCT FROM 'string'
 OR jsonb_typeof(p_data->'expected_revision') IS DISTINCT FROM 'number' OR p_data->>'expected_revision' !~ '^[0-9]{1,9}$'
 OR p_data->>'currency' IS DISTINCT FROM 'USD'
 OR jsonb_typeof(p_data->'evidence_ref') IS DISTINCT FROM 'string' OR length(trim(p_data->>'evidence_ref')) NOT BETWEEN 10 AND 1000
 OR jsonb_typeof(p_data->'evidence_hash') IS DISTINCT FROM 'string' OR p_data->>'evidence_hash' !~ '^[a-f0-9]{64}$'
 OR jsonb_typeof(p_data->'external_campaign_id') IS DISTINCT FROM 'string' OR jsonb_typeof(p_data->'ad_account_id') IS DISTINCT FROM 'string' THEN
  RAISE EXCEPTION 'Invalid cost evidence shape' USING ERRCODE='22023'; END IF;
 day:=(p_data->>'date')::date; observed:=(p_data->>'observed_at')::timestamptz; coverage:=p_data->>'coverage'; zone:=p_data->>'reporting_timezone'; expected:=(p_data->>'expected_revision')::integer;
 IF NOT isfinite(day) OR NOT isfinite(observed) OR observed>clock_timestamp() OR coverage IS NULL OR coverage NOT IN ('complete','partial','withdrawn')
 OR NOT EXISTS(SELECT 1 FROM pg_timezone_names WHERE name=zone) THEN RAISE EXCEPTION 'Invalid cost date or coverage' USING ERRCODE='22023'; END IF;
 IF coverage='withdrawn' THEN
  IF p_data->'amount_minor' IS DISTINCT FROM 'null'::jsonb THEN RAISE EXCEPTION 'Withdrawn cost must be unavailable' USING ERRCODE='22023'; END IF;
 ELSE
  IF jsonb_typeof(p_data->'amount_minor') IS DISTINCT FROM 'number' OR p_data->>'amount_minor' !~ '^[0-9]{1,15}$' THEN RAISE EXCEPTION 'Exact minor units required' USING ERRCODE='22023'; END IF;
  amount:=(p_data->>'amount_minor')::bigint;
  IF amount>100000000000000 THEN RAISE EXCEPTION 'Cost exceeds supported bound' USING ERRCODE='22023'; END IF;
 END IF;
 IF coverage='complete' AND (observed AT TIME ZONE zone)::date<=day THEN RAISE EXCEPTION 'Complete cost requires closed local day' USING ERRCODE='22023'; END IF;
 PERFORM 1 FROM private.acquisition_activation WHERE singleton FOR SHARE;
 PERFORM 1 FROM public.workspaces WHERE id=p_workspace AND status='active' FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Workspace unavailable' USING ERRCODE='42501'; END IF;
 PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id JOIN auth.sessions s ON s.user_id=p.id
 WHERE m.workspace_id=p_workspace AND m.user_id=auth.uid() AND m.status='active' AND m.role IN ('owner','admin') AND p.status='approved'
 AND s.id::text=auth.jwt()->>'session_id' AND (s.not_after IS NULL OR s.not_after>clock_timestamp()) FOR SHARE OF m,p,s;
 IF NOT FOUND THEN RAISE EXCEPTION 'Cost review authority changed' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-cost-request:'||p_id::text,0));
 SELECT * INTO saved FROM public.fb_campaign_performance WHERE id=p_id;
 IF FOUND THEN
  IF ROW(saved.workspace_id,saved.acquisition_link_review_id,saved.acquisition_data,saved.acquisition_actor_id) IS DISTINCT FROM ROW(p_workspace,p_link_review,p_data,auth.uid()) THEN
   RAISE EXCEPTION 'Cost request conflict' USING ERRCODE='23505'; END IF;
  RETURN jsonb_build_object('id',saved.id,'campaign_id',saved.acquisition_campaign_id,'revision',saved.acquisition_revision,'duplicate',true,'execution_authorized',false);
 END IF;
 SELECT * INTO review FROM public.acquisition_campaign_links WHERE id=p_link_review AND workspace_id=p_workspace AND action='link';
 IF NOT FOUND OR review.external_campaign_id IS DISTINCT FROM p_data->>'external_campaign_id' OR review.ad_account_id IS DISTINCT FROM p_data->>'ad_account_id' THEN
  RAISE EXCEPTION 'Cost campaign account mismatch' USING ERRCODE='42501'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('facebook-campaign-link:'||review.external_campaign_id,0));
 PERFORM 1 FROM private.acquisition_integrations WHERE id=review.integration_id FOR SHARE;
 PERFORM 1 FROM public.workspace_memberships m JOIN public.profiles p ON p.id=m.user_id WHERE m.workspace_id=p_workspace AND m.user_id=review.actor_id FOR SHARE OF m,p;
 PERFORM 1 FROM public.ad_campaigns WHERE id=review.campaign_id AND workspace_id=p_workspace FOR SHARE;
 state:=private.acquisition_campaign_link_state(p_workspace,review.intake_id);
 IF state->'link_current' IS DISTINCT FROM 'true'::jsonb OR state->'latest_review'->>'id' IS DISTINCT FROM p_link_review::text THEN
  RAISE EXCEPTION 'Current reviewed campaign required' USING ERRCODE='40001'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('acquisition-cost-campaign:'||review.campaign_id::text,0));
 -- A campaign has one reporting timezone; silently mixing account calendars is forbidden.
 IF EXISTS(SELECT 1 FROM public.fb_campaign_performance WHERE workspace_id=p_workspace AND acquisition_campaign_id=review.campaign_id AND (acquisition_timezone<>zone OR acquisition_data->>'external_campaign_id' IS DISTINCT FROM p_data->>'external_campaign_id' OR acquisition_data->>'ad_account_id' IS DISTINCT FROM p_data->>'ad_account_id')) THEN
  RAISE EXCEPTION 'Campaign reporting identity or timezone conflict' USING ERRCODE='22023'; END IF;
 SELECT coalesce(max(acquisition_revision),0) INTO seq FROM public.fb_campaign_performance WHERE workspace_id=p_workspace AND acquisition_campaign_id=review.campaign_id AND date=day;
 IF seq<>expected THEN RAISE EXCEPTION 'Cost revision changed' USING ERRCODE='40001'; END IF;
 INSERT INTO public.fb_campaign_performance(id,date,campaign_id,ad_set_id,spend,leads,contact_rate,appt_rate,frequency,
  workspace_id,acquisition_campaign_id,acquisition_link_review_id,acquisition_revision,acquisition_amount_minor,acquisition_coverage,acquisition_timezone,acquisition_observed_at,acquisition_data,acquisition_actor_id,acquisition_recorded_at)
 VALUES(p_id,day,NULL,NULL,NULL,NULL,NULL,NULL,NULL,p_workspace,review.campaign_id,p_link_review,seq+1,amount,coverage,zone,observed,p_data,auth.uid(),clock_timestamp());
 INSERT INTO public.audit_logs(entity_type,entity_id,action,actor,new_value,workspace_id)
 VALUES('acquisition_cost',p_id::text,'evidence_recorded',auth.uid()::text,jsonb_build_object('campaign_id',review.campaign_id,'link_review_id',p_link_review,'date',day,'revision',seq+1,'coverage',coverage,'evidence_hash',p_data->>'evidence_hash','basis','reviewed_import','execution_authorized',false),p_workspace);
 RETURN jsonb_build_object('id',p_id,'campaign_id',review.campaign_id,'revision',seq+1,'duplicate',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.record_acquisition_cost(p_id uuid,p_workspace uuid,p_link_review uuid,p_data jsonb)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER SET search_path='' AS $$ SELECT private.record_acquisition_cost(p_id,p_workspace,p_link_review,p_data) $$;
REVOKE ALL ON FUNCTION private.record_acquisition_cost(uuid,uuid,uuid,jsonb),public.record_acquisition_cost(uuid,uuid,uuid,jsonb) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.record_acquisition_cost(uuid,uuid,uuid,jsonb),public.record_acquisition_cost(uuid,uuid,uuid,jsonb) TO authenticated;

CREATE FUNCTION private.protect_acquisition_cost() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE scoped boolean; function_owner text;
BEGIN
 scoped:=CASE WHEN TG_OP='DELETE' THEN OLD.workspace_id IS NOT NULL ELSE NEW.workspace_id IS NOT NULL END;
 IF TG_OP='UPDATE' THEN scoped:=scoped OR OLD.workspace_id IS NOT NULL; END IF;
 IF NOT scoped THEN RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END; END IF;
 IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Cost evidence is immutable' USING ERRCODE='42501'; END IF;
 SELECT pg_get_userbyid(proowner) INTO function_owner FROM pg_proc WHERE oid='private.record_acquisition_cost(uuid,uuid,uuid,jsonb)'::regprocedure;
 IF current_user<>function_owner THEN RAISE EXCEPTION 'Use reviewed cost function' USING ERRCODE='42501'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION private.protect_acquisition_cost() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER protect_acquisition_cost BEFORE INSERT OR UPDATE OR DELETE ON public.fb_campaign_performance FOR EACH ROW EXECUTE FUNCTION private.protect_acquisition_cost();
CREATE FUNCTION private.acquisition_cost_evidence(p_workspace uuid,p_campaign uuid,p_start date,p_end date,p_as_of timestamptz)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path='' AS $$
DECLARE row public.fb_campaign_performance%ROWTYPE; review public.acquisition_campaign_links%ROWTYPE; state jsonb;
 items jsonb:='[]'::jsonb; current_link boolean; zone text;
BEGIN
 IF coalesce(private.acquisition_role(p_workspace),'') NOT IN ('owner','admin','operator') THEN RAISE EXCEPTION 'Workspace cost reporting access required' USING ERRCODE='42501'; END IF;
 IF p_start IS NULL OR p_end IS NULL OR NOT isfinite(p_start) OR NOT isfinite(p_end) OR p_end<p_start OR p_end-p_start>365
 OR p_as_of IS NULL OR NOT isfinite(p_as_of) OR p_as_of>statement_timestamp() THEN RAISE EXCEPTION 'Invalid cost reporting window' USING ERRCODE='22023'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.ad_campaigns WHERE id=p_campaign AND workspace_id=p_workspace AND acquisition_channel='facebook') THEN RAISE EXCEPTION 'Scoped Facebook campaign required' USING ERRCODE='42501'; END IF;
 SELECT acquisition_timezone INTO zone FROM public.fb_campaign_performance WHERE workspace_id=p_workspace AND acquisition_campaign_id=p_campaign ORDER BY acquisition_recorded_at,id LIMIT 1;
 FOR row IN SELECT DISTINCT ON (date) * FROM public.fb_campaign_performance WHERE workspace_id=p_workspace AND acquisition_campaign_id=p_campaign
 AND date BETWEEN p_start AND p_end AND acquisition_observed_at<=p_as_of AND acquisition_recorded_at<=p_as_of ORDER BY date,acquisition_revision DESC LOOP
  SELECT * INTO review FROM public.acquisition_campaign_links WHERE workspace_id=p_workspace AND id=row.acquisition_link_review_id;
  current_link:=false;
  BEGIN
   state:=private.acquisition_campaign_link_state(p_workspace,review.intake_id);
   current_link:=coalesce(state->'link_current'='true'::jsonb AND state->'latest_review'->>'id'=review.id::text,false);
  EXCEPTION WHEN SQLSTATE '55000' THEN current_link:=false;
  END;
  items:=items||jsonb_build_array(jsonb_build_object('id',row.id,'workspace_id',p_workspace,'campaign_id',p_campaign,
   'date',row.date,'revision',row.acquisition_revision,'amount_minor',row.acquisition_amount_minor,'coverage',row.acquisition_coverage,
   'reporting_timezone',row.acquisition_timezone,'currency','USD','observed_at',row.acquisition_observed_at,
   'evidence_ref','persisted-cost-record:'||row.id::text,'evidence_hash',row.acquisition_data->>'evidence_hash',
   'link_review_id',row.acquisition_link_review_id,'attribution_current',current_link,'basis','reviewed_import'));
 END LOOP;
 RETURN jsonb_build_object('workspace_id',p_workspace,'campaign_id',p_campaign,'start_date',p_start,'end_date',p_end,'as_of',p_as_of,
 'reporting_timezone',zone,'currency','USD','items',items,'truncated',false,'execution_authorized',false);
END $$;
CREATE FUNCTION public.acquisition_cost_evidence(p_workspace uuid,p_campaign uuid,p_start date,p_end date,p_as_of timestamptz)
RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path='' AS $$ SELECT private.acquisition_cost_evidence(p_workspace,p_campaign,p_start,p_end,p_as_of) $$;
REVOKE ALL ON FUNCTION private.acquisition_cost_evidence(uuid,uuid,date,date,timestamptz),public.acquisition_cost_evidence(uuid,uuid,date,date,timestamptz) FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION private.acquisition_cost_evidence(uuid,uuid,date,date,timestamptz),public.acquisition_cost_evidence(uuid,uuid,date,date,timestamptz) TO authenticated;
COMMIT;
