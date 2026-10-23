BEGIN;
DO $$
DECLARE lead uuid:=gen_random_uuid(); property uuid:=gen_random_uuid(); run uuid:=gen_random_uuid(); signal uuid:=gen_random_uuid(); evaluation uuid:=gen_random_uuid(); source uuid; v jsonb; h text; result jsonb; token uuid; empty_part jsonb:='{"points":0,"reason":"Unknown evidence","evidence_ids":[]}'::jsonb;
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

 v:=public.prepare_list_score_job(evaluation,lead,'claude-synthetic');
 IF v#>>'{job,state}' IS DISTINCT FROM 'queued' THEN RAISE EXCEPTION 'Prepare failed: %',v; END IF;
 v:=public.claim_list_score_job(evaluation); token:=(v#>>'{job,claim_token}')::uuid;
 IF v->>'dispatch' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'Claim failed'; END IF;
 v:=public.claim_list_score_job(evaluation);
 IF v->>'dispatch' IS DISTINCT FROM 'false' THEN RAISE EXCEPTION 'Duplicate dispatch'; END IF;
 v:=public.receive_list_score_job(evaluation,token,'claude-synthetic','synthetic-receipt',result);
 IF v#>>'{job,state}' IS DISTINCT FROM 'received' THEN RAISE EXCEPTION 'Receipt not durable'; END IF;
 v:=public.prepare_list_score_job(evaluation,lead,'claude-synthetic');
 IF v#>>'{job,state}' IS DISTINCT FROM 'received' THEN RAISE EXCEPTION 'Restart lost receipt'; END IF;
 v:=public.complete_list_score_job(evaluation);
 IF v#>>'{job,state}' IS DISTINCT FROM 'completed' OR (v#>>'{evaluation,score}')::int IS DISTINCT FROM 7 THEN RAISE EXCEPTION 'Completion failed: %',v; END IF;
 v:=public.complete_list_score_job(evaluation);
 IF v->>'replayed' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'Completion replay failed'; END IF;
 IF has_function_privilege('authenticated','public.claim_list_score_job(uuid)','execute')
 OR has_function_privilege('anon','public.receive_list_score_job(uuid,uuid,text,text,jsonb)','execute')
 OR has_table_privilege('service_role','wholesale_ingest.scoring_jobs','DELETE') THEN RAISE EXCEPTION 'Unsafe scoring job privileges'; END IF;
END $$;
ROLLBACK;
SELECT 'scoring job rollback passed' AS result;
