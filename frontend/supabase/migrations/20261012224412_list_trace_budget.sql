-- Service-only reservations; no provider call or live budget activation.
ALTER TABLE wholesale_ingest.skip_trace_requests
 ADD COLUMN input_hash text CHECK(input_hash ~ '^[a-f0-9]{64}$'),
 ADD COLUMN result_hash text CHECK(result_hash ~ '^[a-f0-9]{64}$'),
 ADD COLUMN settled_at timestamptz;
CREATE UNIQUE INDEX trace_one_unresolved_lead ON wholesale_ingest.skip_trace_requests(lead_id)
 WHERE state IN ('reserved','submitted','unknown');

CREATE FUNCTION public.reserve_list_trace(p_id uuid,p_lead uuid,p_provider text,p_input_hash text,p_max_cents integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved wholesale_ingest.skip_trace_requests; budget wholesale_ingest.daily_budgets;
 day date:=(clock_timestamp() AT TIME ZONE 'America/Chicago')::date; lead_json jsonb;
BEGIN
 IF p_id IS NULL OR p_lead IS NULL OR coalesce(p_provider,'') !~ '^[a-z0-9_-]{1,64}$'
 OR coalesce(p_input_hash,'') !~ '^[a-f0-9]{64}$' OR p_max_cents IS NULL OR p_max_cents<=0
 THEN RETURN jsonb_build_object('blocked','invalid_request'); END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended('trace-request:'||p_id::text,0));
 PERFORM pg_advisory_xact_lock(hashtextextended('trace-lead:'||p_lead::text,0));
 SELECT * INTO saved FROM wholesale_ingest.skip_trace_requests WHERE id=p_id;
 IF FOUND THEN
  IF saved.lead_id<>p_lead OR saved.provider<>p_provider OR saved.input_hash IS DISTINCT FROM p_input_hash
   OR saved.reserved_cents<>p_max_cents THEN RETURN jsonb_build_object('blocked','reference_conflict'); END IF;
  RETURN jsonb_build_object('request',to_jsonb(saved),'replayed',true,'dispatch',false);
 END IF;
 SELECT to_jsonb(l) INTO lead_json FROM public.leads l WHERE id=p_lead FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','lead_missing'); END IF;
 IF NOT EXISTS(SELECT 1 FROM wholesale_ingest.properties WHERE lead_id=p_lead AND state='TX' AND county IN ('Dallas','Collin'))
 THEN RETURN jsonb_build_object('blocked','unverified_pipeline_property'); END IF;
 IF coalesce(nullif(trim(lead_json->>'owner_phone_1'),''),nullif(trim(lead_json->>'owner_phone_2'),''),nullif(trim(lead_json->>'owner_email'),'')) IS NOT NULL
 OR EXISTS(SELECT 1 FROM wholesale_ingest.contacts WHERE lead_id=p_lead AND expires_at>clock_timestamp())
 OR EXISTS(SELECT 1 FROM wholesale_ingest.skip_trace_requests WHERE lead_id=p_lead AND state='completed')
 THEN RETURN jsonb_build_object('blocked','already_enriched'); END IF;
 IF EXISTS(SELECT 1 FROM wholesale_ingest.skip_trace_requests WHERE lead_id=p_lead AND state IN ('reserved','submitted','unknown'))
 THEN RETURN jsonb_build_object('blocked','unresolved_request'); END IF;
 SELECT * INTO budget FROM wholesale_ingest.daily_budgets WHERE spend_day=day FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','budget_not_configured'); END IF;
 IF p_max_cents::bigint+budget.reserved_cents+budget.actual_cents>budget.cap_cents
 THEN RETURN jsonb_build_object('blocked','daily_cap'); END IF;
 INSERT INTO wholesale_ingest.skip_trace_requests(id,lead_id,provider,request_key,spend_day,reserved_cents,state,input_hash)
 VALUES(p_id,p_lead,p_provider,p_id::text,day,p_max_cents,'reserved',p_input_hash) RETURNING * INTO saved;
 UPDATE wholesale_ingest.daily_budgets SET reserved_cents=reserved_cents+p_max_cents WHERE spend_day=day;
 RETURN jsonb_build_object('request',to_jsonb(saved),'replayed',false,'dispatch',false);
END $$;

CREATE FUNCTION public.claim_list_trace(p_id uuid,p_input_hash text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved wholesale_ingest.skip_trace_requests;
BEGIN
 IF coalesce(p_input_hash,'') !~ '^[a-f0-9]{64}$' THEN RETURN jsonb_build_object('blocked','invalid_input_identity'); END IF;
 SELECT * INTO saved FROM wholesale_ingest.skip_trace_requests WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','request_missing'); END IF;
 IF saved.input_hash IS DISTINCT FROM p_input_hash THEN RETURN jsonb_build_object('blocked','input_changed'); END IF;
 IF saved.state<>'reserved' THEN RETURN jsonb_build_object('request',to_jsonb(saved),'dispatch',false); END IF;
 -- Reservation may not cross the spend-day boundary into a new uncapped day.
 IF saved.spend_day<>(clock_timestamp() AT TIME ZONE 'America/Chicago')::date
 THEN RETURN jsonb_build_object('blocked','reservation_expired'); END IF;
 UPDATE wholesale_ingest.skip_trace_requests SET state='submitted' WHERE id=p_id RETURNING * INTO saved;
 RETURN jsonb_build_object('request',to_jsonb(saved),'dispatch',true);
END $$;

CREATE FUNCTION public.settle_list_trace(p_id uuid,p_state text,p_actual_cents integer,p_provider_receipt text,p_result_hash text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved wholesale_ingest.skip_trace_requests;
BEGIN
 SELECT * INTO saved FROM wholesale_ingest.skip_trace_requests WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','request_missing'); END IF;
 IF p_state='unknown' AND p_actual_cents IS NULL AND p_provider_receipt IS NULL AND p_result_hash IS NULL THEN
  IF saved.state IN ('submitted','unknown') THEN
   UPDATE wholesale_ingest.skip_trace_requests SET state='unknown' WHERE id=p_id RETURNING * INTO saved;
   RETURN jsonb_build_object('request',to_jsonb(saved),'dispatch',false);
  END IF;
  RETURN jsonb_build_object('blocked','invalid_transition');
 END IF;
 IF p_state IS NULL OR p_state NOT IN ('completed','failed') OR p_actual_cents IS NULL
 OR p_actual_cents<0 OR p_actual_cents>saved.reserved_cents
 OR coalesce(length(trim(p_provider_receipt)),0) NOT BETWEEN 1 AND 255
 OR coalesce(p_result_hash,'') !~ '^[a-f0-9]{64}$'
 THEN RETURN jsonb_build_object('blocked','unconfirmed_settlement'); END IF;
 IF saved.state IN ('completed','failed') THEN
  IF saved.state<>p_state OR saved.actual_cents<>p_actual_cents OR saved.provider_job_id IS DISTINCT FROM p_provider_receipt
   OR saved.result_hash IS DISTINCT FROM p_result_hash THEN RETURN jsonb_build_object('blocked','settlement_conflict'); END IF;
  RETURN jsonb_build_object('request',to_jsonb(saved),'replayed',true,'dispatch',false);
 END IF;
 IF saved.state NOT IN ('submitted','unknown') THEN RETURN jsonb_build_object('blocked','invalid_transition'); END IF;
 -- Hold the original day's budget through provider ambiguity, even after midnight.
 PERFORM 1 FROM wholesale_ingest.daily_budgets WHERE spend_day=saved.spend_day FOR UPDATE;
 UPDATE wholesale_ingest.daily_budgets SET reserved_cents=reserved_cents-saved.reserved_cents,
  actual_cents=actual_cents+p_actual_cents WHERE spend_day=saved.spend_day;
 IF NOT FOUND THEN RAISE EXCEPTION 'Original trace budget missing'; END IF;
 UPDATE wholesale_ingest.skip_trace_requests SET state=p_state,actual_cents=p_actual_cents,
  provider_job_id=p_provider_receipt,result_hash=p_result_hash,settled_at=clock_timestamp() WHERE id=p_id RETURNING * INTO saved;
 RETURN jsonb_build_object('request',to_jsonb(saved),'replayed',false,'dispatch',false);
END $$;
REVOKE ALL ON FUNCTION public.reserve_list_trace(uuid,uuid,text,text,integer),public.claim_list_trace(uuid,text),public.settle_list_trace(uuid,text,integer,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_list_trace(uuid,uuid,text,text,integer),public.claim_list_trace(uuid,text),public.settle_list_trace(uuid,text,integer,text,text) TO service_role;

CREATE FUNCTION public.cancel_reserved_list_trace(p_id uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE saved wholesale_ingest.skip_trace_requests;
BEGIN
 SELECT * INTO saved FROM wholesale_ingest.skip_trace_requests WHERE id=p_id FOR UPDATE;
 IF NOT FOUND THEN RETURN jsonb_build_object('blocked','request_missing'); END IF;
 IF saved.state<>'reserved' THEN RETURN jsonb_build_object('blocked','already_claimed'); END IF;
 UPDATE wholesale_ingest.daily_budgets SET reserved_cents=reserved_cents-saved.reserved_cents WHERE spend_day=saved.spend_day;
 IF NOT FOUND THEN RAISE EXCEPTION 'Original trace budget missing'; END IF;
 UPDATE wholesale_ingest.skip_trace_requests SET state='failed',actual_cents=0,provider_job_id='not_submitted',
  result_hash=input_hash,settled_at=clock_timestamp() WHERE id=p_id RETURNING * INTO saved;
 RETURN jsonb_build_object('request',to_jsonb(saved),'dispatch',false);
END $$;
REVOKE ALL ON FUNCTION public.cancel_reserved_list_trace(uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.cancel_reserved_list_trace(uuid) TO service_role;

CREATE FUNCTION wholesale_ingest.protect_trace_identity() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF ROW(NEW.id,NEW.lead_id,NEW.provider,NEW.request_key,NEW.spend_day,NEW.reserved_cents,NEW.input_hash)
 IS DISTINCT FROM ROW(OLD.id,OLD.lead_id,OLD.provider,OLD.request_key,OLD.spend_day,OLD.reserved_cents,OLD.input_hash)
 THEN RAISE EXCEPTION 'Trace reservation identity is immutable'; END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION wholesale_ingest.protect_trace_identity() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER trace_identity_immutable BEFORE UPDATE ON wholesale_ingest.skip_trace_requests
 FOR EACH ROW EXECUTE FUNCTION wholesale_ingest.protect_trace_identity();
REVOKE INSERT,UPDATE,DELETE ON wholesale_ingest.skip_trace_requests,wholesale_ingest.daily_budgets FROM wholesale_worker;
