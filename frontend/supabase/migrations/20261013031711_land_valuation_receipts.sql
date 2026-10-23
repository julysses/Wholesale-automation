ALTER TABLE public.land_comps ADD COLUMN revision integer NOT NULL DEFAULT 0;
ALTER TABLE public.land_comps ADD COLUMN tav_assessment_date date;
CREATE INDEX land_comps_latest ON public.land_comps(land_lead_id,created_at DESC,id DESC);
ALTER TABLE public.land_comps ENABLE ROW LEVEL SECURITY;
REVOKE INSERT,UPDATE,DELETE ON public.land_comps FROM PUBLIC,anon,authenticated;
CREATE POLICY valuation_api_insert_only ON public.land_comps AS RESTRICTIVE FOR INSERT TO authenticated WITH CHECK(false);
CREATE POLICY valuation_api_update_only ON public.land_comps AS RESTRICTIVE FOR UPDATE TO authenticated USING(false) WITH CHECK(false);
CREATE POLICY valuation_api_delete_only ON public.land_comps AS RESTRICTIVE FOR DELETE TO authenticated USING(false);
GRANT SELECT,INSERT,UPDATE ON public.land_comps TO service_role;
CREATE FUNCTION wholesale_ingest.version_land_valuation() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
BEGIN
 IF NEW.id IS DISTINCT FROM OLD.id OR NEW.land_lead_id IS DISTINCT FROM OLD.land_lead_id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN RAISE EXCEPTION 'Immutable valuation identity'; END IF;
 NEW.revision:=OLD.revision+1;RETURN NEW;
END $$;
CREATE TRIGGER version_land_valuation BEFORE UPDATE ON public.land_comps FOR EACH ROW EXECUTE FUNCTION wholesale_ingest.version_land_valuation();
CREATE TABLE wholesale_ingest.land_valuation_events (
 id uuid PRIMARY KEY,operator_id uuid NOT NULL REFERENCES public.profiles(id),land_lead_id uuid NOT NULL REFERENCES public.land_leads(id),
 comp_id uuid NOT NULL REFERENCES public.land_comps(id),expected_hash text NOT NULL,payload jsonb NOT NULL,saved_snapshot jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
ALTER TABLE wholesale_ingest.land_valuation_events ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.land_valuation_events FROM PUBLIC,anon,authenticated,wholesale_worker;
GRANT SELECT,INSERT ON wholesale_ingest.land_valuation_events TO service_role;
CREATE FUNCTION wholesale_ingest.immutable_land_valuation_event() RETURNS trigger LANGUAGE plpgsql SET search_path='' AS $$
BEGIN RAISE EXCEPTION 'Immutable valuation receipt'; END $$;
CREATE TRIGGER immutable_land_valuation_event BEFORE UPDATE OR DELETE ON wholesale_ingest.land_valuation_events FOR EACH ROW EXECUTE FUNCTION wholesale_ingest.immutable_land_valuation_event();

CREATE FUNCTION wholesale_ingest.land_valuation_snapshot(p_land uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE land public.land_leads;comp public.land_comps;records integer;doc jsonb;
BEGIN
 SELECT * INTO land FROM public.land_leads WHERE id=p_land;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','land_missing'); END IF;
 SELECT * INTO comp FROM public.land_comps WHERE land_lead_id=p_land ORDER BY created_at DESC,id DESC LIMIT 1;
 SELECT count(*) INTO records FROM public.land_comps WHERE land_lead_id=p_land;
 doc:=jsonb_build_object('land',to_jsonb(land),'comp',CASE WHEN comp.id IS NOT NULL THEN to_jsonb(comp) END,'record_count',records);
 RETURN jsonb_build_object('land_lead_id',p_land,'snapshot_hash',encode(sha256(convert_to(doc::text,'UTF8')),'hex'),
 'comp',doc->'comp','record_count',records,'reference_tav',to_jsonb(land)->'tav','property_address',land.property_address,'outreach_authorized',false);
END $$;
CREATE FUNCTION public.read_land_valuation(p_land uuid,p_operator uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved') THEN RAISE EXCEPTION 'Approved operator required'; END IF;
 RETURN wholesale_ingest.land_valuation_snapshot(p_land);
END $$;
CREATE FUNCTION wholesale_ingest.valid_land_valuation(p jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE r jsonb;k text;v numeric;today date:=(now() AT TIME ZONE 'America/Chicago')::date;
 keys text[]:=ARRAY['direct_comp_details','avg_house_arv','house_comp_count','tav','tav_source','tav_assessment_date','comp_notes'];
BEGIN
 IF jsonb_typeof(p) IS DISTINCT FROM 'object' OR NOT(p ?& keys) OR (p-keys)<>'{}'::jsonb
 OR jsonb_typeof(p->'direct_comp_details') IS DISTINCT FROM 'array' OR jsonb_array_length(p->'direct_comp_details')>50
 OR jsonb_typeof(p->'comp_notes') IS DISTINCT FROM 'string' OR length(p->>'comp_notes')>10000
 OR p->>'tav_source' IS NULL OR p->>'tav_source' NOT IN ('county','xleads','manual') THEN RETURN false; END IF;
 FOREACH k IN ARRAY ARRAY['avg_house_arv','tav'] LOOP
  IF p->k<>'null'::jsonb THEN
   IF jsonb_typeof(p->k)<>'number' THEN RETURN false; END IF;
   v:=(p->>k)::numeric;
   IF v<0 OR v>9999999999.99 OR v<>round(v,2) OR (k='avg_house_arv' AND v=0) THEN RETURN false; END IF;
  END IF;
 END LOOP;
 IF p->'avg_house_arv'='null'::jsonb THEN
  IF p->'house_comp_count'<>'null'::jsonb THEN RETURN false; END IF;
 ELSE
  IF jsonb_typeof(p->'house_comp_count') IS DISTINCT FROM 'number' THEN RETURN false; END IF;
  v:=(p->>'house_comp_count')::numeric;IF v<1 OR v>10000 OR v<>trunc(v) THEN RETURN false; END IF;
 END IF;
 IF p->'tav_assessment_date'<>'null'::jsonb THEN
  IF p->'tav'='null'::jsonb OR jsonb_typeof(p->'tav_assessment_date')<>'string' OR (p->>'tav_assessment_date') !~ '^\d{4}-\d{2}-\d{2}$'
   OR (p->>'tav_assessment_date')::date>today THEN RETURN false; END IF;
 END IF;
 FOR r IN SELECT value FROM jsonb_array_elements(p->'direct_comp_details') LOOP
  IF jsonb_typeof(r) IS DISTINCT FROM 'object' OR NOT(r ?& ARRAY['address','price','sqft','date','distance_mi','source_url'])
   OR (r-ARRAY['address','price','sqft','date','distance_mi','source_url'])<>'{}'::jsonb
   OR jsonb_typeof(r->'address') IS DISTINCT FROM 'string' OR length(trim(r->>'address')) NOT BETWEEN 1 AND 500
   OR jsonb_typeof(r->'price') IS DISTINCT FROM 'number' THEN RETURN false; END IF;
  v:=(r->>'price')::numeric;IF v<=0 OR v>9999999999.99 OR v<>round(v,2) THEN RETURN false; END IF;
  FOREACH k IN ARRAY ARRAY['sqft','distance_mi'] LOOP
   IF r->k<>'null'::jsonb THEN
    IF jsonb_typeof(r->k)<>'number' THEN RETURN false; END IF;
    v:=(r->>k)::numeric;
    IF v<0 OR (k='sqft' AND (v=0 OR v>1000000000000)) OR (k='distance_mi' AND v>10000) THEN RETURN false; END IF;
   END IF;
  END LOOP;
  IF r->'date'<>'null'::jsonb AND (jsonb_typeof(r->'date')<>'string' OR (r->>'date') !~ '^\d{4}-\d{2}-\d{2}$' OR (r->>'date')::date>today) THEN RETURN false; END IF;
  IF r->'source_url'<>'null'::jsonb AND (jsonb_typeof(r->'source_url')<>'string' OR length(r->>'source_url')>2000 OR (r->>'source_url') !~ '^https://[^[:space:]]+$') THEN RETURN false; END IF;
 END LOOP;
 RETURN jsonb_array_length(p->'direct_comp_details')>0 OR p->'avg_house_arv'<>'null'::jsonb OR p->'tav'<>'null'::jsonb;
EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow OR invalid_text_representation OR numeric_value_out_of_range THEN RETURN false;
END $$;
CREATE FUNCTION public.save_land_valuation(p_id uuid,p_operator uuid,p_land uuid,p_expected_hash text,p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved wholesale_ingest.land_valuation_events; snapshot jsonb;comp public.land_comps; comp_id uuid;
 direct_count integer;direct_avg numeric;direct_low numeric;direct_high numeric;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=p_operator AND status='approved') THEN RAISE EXCEPTION 'Approved operator required'; END IF;
 IF p_id IS NULL OR p_land IS NULL OR coalesce(p_expected_hash,'') !~ '^[a-f0-9]{64}$' OR wholesale_ingest.valid_land_valuation(p_payload) IS DISTINCT FROM true THEN RETURN jsonb_build_object('blocked','invalid_valuation'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('land-valuation:'||p_id::text,0));
 SELECT * INTO saved FROM wholesale_ingest.land_valuation_events WHERE id=p_id;
 IF FOUND THEN
  IF saved.operator_id<>p_operator OR saved.land_lead_id<>p_land OR saved.expected_hash<>p_expected_hash OR saved.payload IS DISTINCT FROM p_payload THEN RETURN jsonb_build_object('blocked','reference_conflict'); END IF;
  RETURN jsonb_build_object('event',to_jsonb(saved),'replayed',true,'outreach_authorized',false);
 END IF;
 PERFORM 1 FROM public.land_leads WHERE id=p_land FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','land_missing'); END IF;
 SELECT * INTO comp FROM public.land_comps WHERE land_lead_id=p_land ORDER BY created_at DESC,id DESC LIMIT 1 FOR UPDATE;
 snapshot:=wholesale_ingest.land_valuation_snapshot(p_land);
 IF snapshot->>'snapshot_hash' IS DISTINCT FROM p_expected_hash THEN RETURN jsonb_build_object('blocked','valuation_changed'); END IF;
 SELECT count(*)::integer,round(avg((r->>'price')::numeric),2),min((r->>'price')::numeric),max((r->>'price')::numeric)
 INTO direct_count,direct_avg,direct_low,direct_high FROM jsonb_array_elements(p_payload->'direct_comp_details') r;
 comp_id:=comp.id;
 IF comp_id IS NULL THEN
  INSERT INTO public.land_comps(land_lead_id,comped_by) VALUES(p_land,p_operator) RETURNING id INTO comp_id;
 END IF;
 UPDATE public.land_comps SET comped_by=p_operator,direct_comp_details=p_payload->'direct_comp_details',direct_comp_count=direct_count,
 direct_comp_avg=direct_avg,direct_comp_low=direct_low,direct_comp_high=direct_high,
 avg_house_arv=(p_payload->>'avg_house_arv')::numeric,arv_15pct_value=round((p_payload->>'avg_house_arv')::numeric*0.15,2),
 house_comp_count=(p_payload->>'house_comp_count')::numeric::integer,house_comp_radius_mi=0.5,
 tav=(p_payload->>'tav')::numeric,tav_source=p_payload->>'tav_source',tav_assessment_date=(p_payload->>'tav_assessment_date')::date,comp_notes=p_payload->>'comp_notes'
 WHERE id=comp_id;
 snapshot:=wholesale_ingest.land_valuation_snapshot(p_land);
 INSERT INTO wholesale_ingest.land_valuation_events(id,operator_id,land_lead_id,comp_id,expected_hash,payload,saved_snapshot)
 VALUES(p_id,p_operator,p_land,comp_id,p_expected_hash,p_payload,snapshot) RETURNING * INTO saved;
 RETURN jsonb_build_object('event',to_jsonb(saved),'replayed',false,'outreach_authorized',false);
END $$;
REVOKE ALL ON FUNCTION wholesale_ingest.land_valuation_snapshot(uuid),wholesale_ingest.valid_land_valuation(jsonb),public.read_land_valuation(uuid,uuid),public.save_land_valuation(uuid,uuid,uuid,text,jsonb) FROM PUBLIC,anon,authenticated,wholesale_worker;
GRANT EXECUTE ON FUNCTION wholesale_ingest.land_valuation_snapshot(uuid),wholesale_ingest.valid_land_valuation(jsonb),public.read_land_valuation(uuid,uuid),public.save_land_valuation(uuid,uuid,uuid,text,jsonb) TO service_role;
