BEGIN;
SET LOCAL statement_timeout='15s';
DO $$
DECLARE lead uuid:=gen_random_uuid(); property uuid:=gen_random_uuid(); run uuid:=gen_random_uuid(); signal uuid:=gen_random_uuid(); evaluation uuid:=gen_random_uuid(); source uuid; v jsonb; h text; result jsonb; token uuid; actor uuid; handoff uuid:=gen_random_uuid(); land uuid; task uuid; empty_part jsonb:='{"points":0,"reason":"Unknown evidence","evidence_ids":[]}'::jsonb;
BEGIN
 SELECT id INTO actor FROM public.profiles WHERE role='admin' AND status='approved' LIMIT 1;
 IF actor IS NULL THEN RAISE EXCEPTION 'Rehearsal administrator required'; END IF;
 UPDATE wholesale_ingest.settings SET score_threshold=7;
 UPDATE public.app_settings SET value=actor::text WHERE key='lead_owner_user_id';
 IF NOT FOUND THEN INSERT INTO public.app_settings(key,value) VALUES('lead_owner_user_id',actor::text); END IF;
 SELECT id INTO source FROM wholesale_ingest.sources WHERE source_key='tx-dallas-pre_foreclosure';
 INSERT INTO public.leads(id,property_address,city) VALUES(lead,'SYNTHETIC SCORING ROLLBACK QA','Dallas');
 INSERT INTO wholesale_ingest.properties(id,state,county,address_std,city,lead_id) VALUES(property,'TX','Dallas','SYNTHETIC SCORING ROLLBACK QA','Dallas',lead);
 INSERT INTO wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,status,status_reason,manifest_hash,expected_batches)
 VALUES(run,source,current_date,now(),'success','synthetic',repeat('a',64),1);
 INSERT INTO wholesale_ingest.distress_signals(id,property_id,source_id,source_record_id,list_type,filed_date,source_url,first_run_id,last_run_id)
 VALUES(signal,property,source,'synthetic','pre_foreclosure',(now() AT TIME ZONE 'America/Chicago')::date,'https://example.invalid/fixture',run,run);
 v:=public.list_scoring_input(lead); h:=v->>'input_hash';
 v:=public.review_list_lot(gen_random_uuid(),actor,lead,h,true,'https://example.invalid/lot','Synthetic reviewed parcel');
 IF v#>>'{review,is_vacant_lot}' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'Review failed'; END IF;
 result:=jsonb_build_object('components',jsonb_build_object('distress_stack',jsonb_build_object('points',7,'reason','One distinct active list type','evidence_ids',jsonb_build_array(signal)),
 'need_to_sell',empty_part,'equity',empty_part,'contactability',empty_part,'recency',empty_part),'needs_to_sell','unknown');


 v:=public.list_scoring_input(lead);
 v:=public.save_list_score(evaluation,lead,v->>'input_hash','claude-synthetic','daily-list-score-v1','synthetic-worker-receipt',result);
 IF v#>>'{evaluation,route}' IS DISTINCT FROM 'underwrite_lot' THEN RAISE EXCEPTION 'Invalid score'; END IF;
 v:=public.route_list_lots(10);
 SELECT id INTO handoff FROM wholesale_ingest.lot_handoffs WHERE lead_id=lead AND initiation='worker' AND operator_id IS NULL;
 IF handoff IS NULL THEN RAISE EXCEPTION 'Worker did not route: %',v; END IF;
 v:=public.route_list_lots(10);
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(v->'outcomes') o WHERE o->>'lead_id'=lead::text) THEN RAISE EXCEPTION 'Duplicate routing'; END IF;
 v:=wholesale_ingest.scan_lots_at(clock_timestamp()+interval '61 minutes');
 IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(v->'overdue_receipts') entry WHERE entry->>'handoff_id'=handoff::text) THEN RAISE EXCEPTION 'Overdue receipt absent'; END IF;
 v:=public.acknowledge_list_lot(handoff,actor);
 v:=wholesale_ingest.scan_lots_at(clock_timestamp()+interval '62 minutes');
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(v->'overdue_receipts') entry WHERE entry->>'handoff_id'=handoff::text) THEN RAISE EXCEPTION 'Receipt still overdue'; END IF;
 IF has_function_privilege('authenticated','public.route_list_lots(integer)','execute') OR has_function_privilege('anon','public.monitor_list_lots()','execute') THEN RAISE EXCEPTION 'Unsafe worker grants'; END IF;
END $$;
ROLLBACK;
SELECT 'lot worker rollback passed' AS result;
