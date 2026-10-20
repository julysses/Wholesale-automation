BEGIN;
DO $$
DECLARE lead uuid:=gen_random_uuid(); req uuid:=gen_random_uuid(); event uuid:=gen_random_uuid(); actor uuid; v jsonb;
BEGIN
 SELECT id INTO actor FROM public.profiles WHERE role='admin' AND status='approved' LIMIT 1;
 IF actor IS NULL THEN RAISE EXCEPTION 'No approved rehearsal admin'; END IF;
 INSERT INTO public.leads(id,property_address,city,owner_first_name) VALUES(lead,'SYNTHETIC TRACE OPERATIONS ROLLBACK QA','Dallas','Synthetic');
 INSERT INTO wholesale_ingest.properties(state,county,address_std,lead_id) VALUES('TX','Dallas','SYNTHETIC TRACE OPERATIONS ROLLBACK QA',lead);
 INSERT INTO wholesale_ingest.daily_budgets(spend_day,cap_cents) VALUES((clock_timestamp() AT TIME ZONE 'America/Chicago')::date,100);
 v:=public.prepare_list_trace(req,lead,'synthetic',60);
 IF v#>>'{request,state}' IS DISTINCT FROM 'reserved' THEN RAISE EXCEPTION 'Not reserved'; END IF;
 v:=public.cancel_list_trace_as_operator(event,req,actor);
 IF v#>>'{event,result,request,provider_job_id}' IS DISTINCT FROM 'not_submitted' THEN RAISE EXCEPTION 'Cancellation failed'; END IF;
 v:=public.cancel_list_trace_as_operator(event,req,actor);
 IF v->>'replayed' IS DISTINCT FROM 'true' THEN RAISE EXCEPTION 'Replay failed'; END IF;
 v:=public.list_trace_operations(actor,0);
 IF (v->>'open_count')::int<>0 OR (v->>'total_held_cents')::int<>0 THEN RAISE EXCEPTION 'Hold not released'; END IF;
 IF (SELECT count(*) FROM wholesale_ingest.trace_operator_events WHERE id=event)<>1 THEN RAISE EXCEPTION 'Audit duplicated'; END IF;
 IF has_function_privilege('authenticated','public.cancel_list_trace_as_operator(uuid,uuid,uuid)','execute')
 OR has_function_privilege('anon','public.list_trace_operations(uuid,integer)','execute')
 OR has_table_privilege('service_role','wholesale_ingest.trace_operator_events','DELETE') THEN RAISE EXCEPTION 'Unsafe privileges'; END IF;
END $$;
ROLLBACK;
SELECT 'trace operator rollback passed' AS result;
