BEGIN;
DO $$
DECLARE lead uuid:=gen_random_uuid(); property uuid:=gen_random_uuid(); run uuid:=gen_random_uuid(); signal uuid:=gen_random_uuid(); evaluation uuid:=gen_random_uuid(); source uuid; v jsonb; h text; result jsonb; empty_part jsonb:='{"points":0,"reason":"Unknown evidence","evidence_ids":[]}'::jsonb;
BEGIN
 SELECT id INTO source FROM wholesale_ingest.sources WHERE source_key='tx-dallas-pre_foreclosure';
 INSERT INTO public.leads(id,property_address,city) VALUES(lead,'SYNTHETIC SCORING ROLLBACK QA','Dallas');
 INSERT INTO wholesale_ingest.properties(id,state,county,address_std,lead_id) VALUES(property,'TX','Dallas','SYNTHETIC SCORING ROLLBACK QA',lead);
 INSERT INTO wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,status,status_reason,manifest_hash,expected_batches)
 VALUES(run,source,current_date,now(),'success','synthetic',repeat('a',64),1);
 INSERT INTO wholesale_ingest.distress_signals(id,property_id,source_id,source_record_id,list_type,filed_date,source_url,first_run_id,last_run_id)
 VALUES(signal,property,source,'synthetic','pre_foreclosure',(now() AT TIME ZONE 'America/Chicago')::date,'https://example.invalid/fixture',run,run);
 v:=public.list_scoring_input(lead); h:=v->>'input_hash';
 result:=jsonb_build_object('components',jsonb_build_object('distress_stack',jsonb_build_object('points',7,'reason','One distinct active list type','evidence_ids',jsonb_build_array(signal)),
 'need_to_sell',empty_part,'equity',empty_part,'contactability',empty_part,'recency',empty_part),'needs_to_sell','unknown');
 v:=public.save_list_score(evaluation,lead,h,'claude-synthetic','daily-list-score-v1','synthetic-receipt',result);
 IF (v#>>'{evaluation,score}')::int IS DISTINCT FROM 7 OR v->>'outreach_authorized' IS DISTINCT FROM 'false' THEN RAISE EXCEPTION 'Invalid score receipt: %',v; END IF;
 v:=public.save_list_score(evaluation,lead,h,'claude-synthetic','daily-list-score-v1','synthetic-receipt',result);
 IF v->>'replayed' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'Replay failed'; END IF;
 v:=public.scan_list_pipeline();
 IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(v->'top_ten') item WHERE item->>'lead_id'=lead::text) THEN RAISE EXCEPTION 'Current score missing from digest'; END IF;
 UPDATE wholesale_ingest.distress_signals SET filed_date=filed_date-1 WHERE id=signal;
 v:=public.scan_list_pipeline();
 IF EXISTS(SELECT 1 FROM jsonb_array_elements(v->'top_ten') item WHERE item->>'lead_id'=lead::text) THEN RAISE EXCEPTION 'Stale score remains in digest'; END IF;
 v:=public.save_list_score(evaluation,lead,h,'claude-synthetic','daily-list-score-v1','synthetic-receipt',result);
 IF v->>'current' IS DISTINCT FROM 'false' THEN RAISE EXCEPTION 'Historical replay incorrectly current'; END IF;
 IF has_function_privilege('authenticated','public.save_list_score(uuid,uuid,text,text,text,text,jsonb)','execute')
 OR has_function_privilege('anon','public.list_scoring_input(uuid)','execute')
 OR has_table_privilege('service_role','wholesale_ingest.lead_evaluations','UPDATE') THEN RAISE EXCEPTION 'Unsafe scoring privileges'; END IF;
END $$;
ROLLBACK;
SELECT 'list scoring rollback passed' AS result;
