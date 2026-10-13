BEGIN;
DO $$
DECLARE lead uuid:=gen_random_uuid(); property uuid:=gen_random_uuid(); run uuid:=gen_random_uuid(); signal uuid:=gen_random_uuid(); evaluation uuid:=gen_random_uuid(); source uuid; v jsonb; h text; result jsonb; token uuid; actor uuid; handoff uuid:=gen_random_uuid(); land uuid; task uuid; empty_part jsonb:='{"points":0,"reason":"Unknown evidence","evidence_ids":[]}'::jsonb;
BEGIN
 SELECT id INTO actor FROM public.profiles WHERE role='admin' AND status='approved' LIMIT 1;
 IF actor IS NULL THEN RAISE EXCEPTION 'Rehearsal administrator required'; END IF;
 UPDATE wholesale_ingest.settings SET score_threshold=7;
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
 v:=public.handoff_list_lot(handoff,actor,evaluation,actor);
 land:=(v#>>'{handoff,land_lead_id}')::uuid; task:=(v#>>'{handoff,task_id}')::uuid;
 IF land IS NULL OR task IS NULL OR v#>>'{handoff,acknowledged_at}' IS NOT NULL THEN RAISE EXCEPTION 'Handoff failed: %',v; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.land_leads WHERE id=land AND lead_id=lead AND owner_name IS NULL AND offer_price IS NULL AND mao IS NULL AND sms_sequence_active=false AND status='new') THEN RAISE EXCEPTION 'Destination violated unknown or pricing constraints'; END IF;
 v:=public.handoff_list_lot(handoff,actor,evaluation,actor);
 IF v->>'replayed' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'Lost ACK replay failed'; END IF;
 v:=public.handoff_list_lot(gen_random_uuid(),actor,evaluation,actor);
 IF v->>'blocked' IS DISTINCT FROM 'existing_handoff' THEN RAISE EXCEPTION 'Duplicate handoff accepted'; END IF;
 v:=public.list_lot_handoffs(actor,0);
 IF NOT EXISTS(SELECT 1 FROM jsonb_array_elements(v->'handoffs') h WHERE h->>'id'=handoff::text AND h->>'evidence_url'='https://example.invalid/lot' AND h ? 'scoring_input' AND (h->>'score')::int=7) THEN RAISE EXCEPTION 'Receiving evidence missing'; END IF;
 v:=public.acknowledge_list_lot(handoff,actor);
 IF v#>>'{handoff,acknowledged_by}' IS DISTINCT FROM actor::text THEN RAISE EXCEPTION 'Receiving acknowledgement failed'; END IF;
 v:=public.acknowledge_list_lot(handoff,actor);
 IF v->>'replayed' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'Repeated receiving acknowledgement changed receipt'; END IF;
 IF has_function_privilege('anon','public.review_list_lot(uuid,uuid,uuid,text,boolean,text,text)','execute') OR has_function_privilege('authenticated','public.handoff_list_lot(uuid,uuid,uuid,uuid)','execute') THEN RAISE EXCEPTION 'Unsafe lot operation grants'; END IF;
END $$;
ROLLBACK;
SELECT 'lot handoff rollback passed' AS result;
