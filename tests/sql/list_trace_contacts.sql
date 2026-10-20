BEGIN;
DO $$
DECLARE lead uuid:=gen_random_uuid(); req uuid:=gen_random_uuid(); v jsonb; h text; budget wholesale_ingest.daily_budgets;
BEGIN
 INSERT INTO public.leads(id,property_address,city,owner_first_name) VALUES(lead,'SYNTHETIC TRACE BUDGET ROLLBACK QA','Dallas','Synthetic');
 INSERT INTO wholesale_ingest.properties(state,county,address_std,lead_id) VALUES('TX','Dallas','SYNTHETIC TRACE BUDGET ROLLBACK QA',lead);
 INSERT INTO wholesale_ingest.daily_budgets(spend_day,cap_cents) VALUES((clock_timestamp() AT TIME ZONE 'America/Chicago')::date,100);
 v:=public.prepare_list_trace(req,lead,'synthetic',60);
 h:=v#>>'{request,input_hash}';
 IF v#>>'{request,state}'<>'reserved' THEN RAISE EXCEPTION 'Reservation failed: %',v; END IF;
 v:=public.prepare_list_trace(req,lead,'synthetic',60);
 IF v->>'replayed'<>'true' THEN RAISE EXCEPTION 'Replay not durable'; END IF;
 v:=public.claim_list_trace(req,h);
 IF v->>'dispatch'<>'true' THEN RAISE EXCEPTION 'Initial claim failed'; END IF;
 v:=public.settle_list_trace(req,'unknown',NULL,NULL,NULL);
 SELECT * INTO budget FROM wholesale_ingest.daily_budgets WHERE spend_day=(clock_timestamp() AT TIME ZONE 'America/Chicago')::date;
 IF budget.reserved_cents<>60 OR budget.actual_cents<>0 THEN RAISE EXCEPTION 'Uncertainty released budget'; END IF;
 v:=public.claim_list_trace(req,h);
 IF v->>'dispatch'<>'false' THEN RAISE EXCEPTION 'Unknown request resubmitted'; END IF;
 v:=public.complete_list_trace(req,'synthetic',h,40,'synthetic-receipt','[{"email":"fixture@example.invalid"}]'::jsonb);
 IF v#>>'{request,state}'<>'completed' THEN RAISE EXCEPTION 'Settlement failed'; END IF;
 v:=public.complete_list_trace(req,'synthetic',h,40,'synthetic-receipt','[{"email":"fixture@example.invalid"}]'::jsonb);
 IF v->>'replayed'<>'true' THEN RAISE EXCEPTION 'Settlement replay failed'; END IF;
 SELECT * INTO budget FROM wholesale_ingest.daily_budgets WHERE spend_day=(clock_timestamp() AT TIME ZONE 'America/Chicago')::date;
 IF budget.reserved_cents<>0 OR budget.actual_cents<>40 THEN RAISE EXCEPTION 'Settlement billed twice'; END IF;
 IF (SELECT count(*) FROM wholesale_ingest.contacts WHERE trace_request_id=req AND dnc_status='unknown')<>1 THEN RAISE EXCEPTION 'Contact receipt missing or duplicated'; END IF;
 IF has_function_privilege('authenticated','public.reserve_list_trace(uuid,uuid,text,text,integer)','execute')
 OR has_function_privilege('anon','public.claim_list_trace(uuid,text)','execute')
 OR has_table_privilege('wholesale_worker','wholesale_ingest.daily_budgets','UPDATE') THEN RAISE EXCEPTION 'Unsafe trace privileges'; END IF;
END $$;
ROLLBACK;
SELECT 'trace contact receipt rollback passed' AS result;
