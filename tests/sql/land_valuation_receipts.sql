BEGIN;
SET LOCAL statement_timeout='15s';
DO $$
DECLARE actor uuid;land uuid:=gen_random_uuid();request_id uuid:=gen_random_uuid();initial jsonb;v jsonb;latest jsonb;comp uuid;
 p jsonb:='{"direct_comp_details":[{"address":"Synthetic comp","price":100,"sqft":null,"date":null,"distance_mi":0,"source_url":null}],"avg_house_arv":null,"house_comp_count":null,"tav":0,"tav_source":"manual","tav_assessment_date":null,"comp_notes":"Synthetic rollback verification"}';
BEGIN
 SELECT id INTO actor FROM public.profiles WHERE status='approved' LIMIT 1;
 IF actor IS NULL THEN RAISE EXCEPTION 'Approved rehearsal operator required'; END IF;
 INSERT INTO public.land_leads(id,property_address,city,state,county,status,offer_price,mao,sms_sequence_active)
 VALUES(land,'SYNTHETIC VALUATION ROLLBACK QA','Dallas','TX','Dallas','new',12345,23456,false);
 initial:=public.read_land_valuation(land,actor);
 v:=public.save_land_valuation(request_id,actor,land,initial->>'snapshot_hash',p);
 comp:=(v#>>'{event,comp_id}')::uuid;
 IF comp IS NULL OR v#>>'{event,saved_snapshot,comp,direct_comp_avg}' IS DISTINCT FROM '100.00' AND (v#>>'{event,saved_snapshot,comp,direct_comp_avg}')::numeric IS DISTINCT FROM 100 THEN RAISE EXCEPTION 'Valuation save failed'; END IF;
 v:=public.save_land_valuation(request_id,actor,land,initial->>'snapshot_hash',p);
 IF v->>'replayed' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'Replay failed'; END IF;
 v:=public.save_land_valuation(gen_random_uuid(),actor,land,initial->>'snapshot_hash',p);
 IF v->>'blocked' IS DISTINCT FROM 'valuation_changed' THEN RAISE EXCEPTION 'Stale valuation accepted'; END IF;
 UPDATE public.land_comps SET house_comp_radius_mi=0.75 WHERE id=comp;
 latest:=public.read_land_valuation(land,actor);
 v:=public.save_land_valuation(gen_random_uuid(),actor,land,latest->>'snapshot_hash',p||'{"tav":200}'::jsonb);
 v:=public.save_land_valuation(request_id,actor,land,initial->>'snapshot_hash',p);
 latest:=public.read_land_valuation(land,actor);
 IF (latest#>>'{comp,revision}')::integer<>3 OR (latest#>>'{comp,house_comp_radius_mi}')::numeric<>0.75 OR (latest#>>'{comp,tav}')::numeric<>200 OR (latest->>'record_count')::integer<>1 THEN RAISE EXCEPTION 'Historical retry changed current analysis'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.land_leads WHERE id=land AND offer_price=12345 AND mao=23456 AND status='new' AND sms_sequence_active=false) THEN RAISE EXCEPTION 'Pricing or outreach changed'; END IF;
 IF has_function_privilege('authenticated','public.save_land_valuation(uuid,uuid,uuid,text,jsonb)','execute') OR has_table_privilege('authenticated','public.land_comps','UPDATE') OR has_table_privilege('authenticated','public.land_comps','INSERT') THEN RAISE EXCEPTION 'Unsafe valuation grants'; END IF;
END $$;
ROLLBACK;
SELECT 'land valuation rollback passed' AS result;
