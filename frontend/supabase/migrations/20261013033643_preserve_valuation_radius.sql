-- Existing source-radius metadata is not a derived valuation or a user edit here.
CREATE OR REPLACE FUNCTION public.save_land_valuation(p_id uuid,p_operator uuid,p_land uuid,p_expected_hash text,p_payload jsonb) RETURNS jsonb
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
 house_comp_count=(p_payload->>'house_comp_count')::numeric::integer,
 tav=(p_payload->>'tav')::numeric,tav_source=p_payload->>'tav_source',tav_assessment_date=(p_payload->>'tav_assessment_date')::date,comp_notes=p_payload->>'comp_notes'
 WHERE id=comp_id;
 snapshot:=wholesale_ingest.land_valuation_snapshot(p_land);
 INSERT INTO wholesale_ingest.land_valuation_events(id,operator_id,land_lead_id,comp_id,expected_hash,payload,saved_snapshot)
 VALUES(p_id,p_operator,p_land,comp_id,p_expected_hash,p_payload,snapshot) RETURNING * INTO saved;
 RETURN jsonb_build_object('event',to_jsonb(saved),'replayed',false,'outreach_authorized',false);
END $$;
