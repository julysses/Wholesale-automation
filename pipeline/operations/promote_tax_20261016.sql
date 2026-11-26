-- Historical, hash-verified tax snapshots. No active work, property qualification,
-- contact lookup or outreach is imported. Run the exact transaction with ROLLBACK first.
BEGIN;
SET LOCAL lock_timeout='10s';
SET LOCAL statement_timeout='120s';
DO $promotion$
DECLARE
 pid uuid; saved wholesale_ingest.onboarding_promotions; m jsonb;
 target_run uuid; target_source uuid; owner_id uuid:='89f3b3f6-5a88-4b79-b3f4-461e0cd626a2';
 part record; original_run jsonb; actual_hash text; review_task uuid;
 baseline_leads bigint; baseline_properties bigint; baseline_tasks bigint;
 baseline_traces bigint; baseline_sms text; promoted integer:=0;
BEGIN
 IF EXISTS(SELECT 1 FROM wholesale_ingest.sources WHERE enabled)
 OR EXISTS(SELECT 1 FROM wholesale_ingest.settings WHERE outreach_enabled OR daily_trace_cap_cents<>0)
 OR EXISTS(SELECT 1 FROM private.retell_sms_scheduler WHERE enabled)
 THEN RAISE EXCEPTION 'Collection, spending and sending must stay paused'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=owner_id AND role='admin' AND status='approved')
 OR NOT EXISTS(SELECT 1 FROM public.app_settings WHERE key='lead_owner_user_id' AND value=owner_id::text)
 THEN RAISE EXCEPTION 'Approved owner changed'; END IF;
 SELECT count(*) INTO baseline_leads FROM public.leads;
 SELECT count(*) INTO baseline_properties FROM wholesale_ingest.properties;
 SELECT count(*) INTO baseline_tasks FROM public.tasks;
 SELECT count(*) INTO baseline_traces FROM wholesale_ingest.skip_trace_requests;
 SELECT md5(coalesce(string_agg(row_to_json(e)::text,'' ORDER BY e.id),'')) INTO baseline_sms FROM public.sms_events e;
 FOREACH pid IN ARRAY ARRAY['bcb76f65-ceaa-48fb-9ee5-33e010b29d38'::uuid,'79bf66e3-155f-4345-82a1-1a22de9e1500'::uuid] LOOP
  PERFORM pg_advisory_xact_lock(hashtextextended('onboarding-promotion:'||pid::text,0));
  SELECT * INTO STRICT saved FROM wholesale_ingest.onboarding_promotions WHERE id=pid FOR UPDATE;
  IF saved.state='complete' THEN CONTINUE; END IF;
  m:=saved.manifest; target_run:=(m->>'run_id')::uuid; target_source:=(m->>'target_source_id')::uuid;
  original_run:=m->'original_run';
  IF saved.source_project<>'tbhwxgfzbiaqjurghntj' OR saved.operator_id<>owner_id
  OR NOT ((m->>'source_key'='tx-dallas-tax_delinquent' AND target_run='68e93ec1-6e54-4c66-a96b-bd30035de6b7' AND (m->>'records')::int=30516 AND (m->>'batches')::int=62)
   OR (m->>'source_key'='tx-collin-tax_delinquent' AND target_run='892910fa-9b11-4467-993a-d98ae083a8ac' AND (m->>'records')::int=9182 AND (m->>'batches')::int=19))
  OR original_run->>'id'<>target_run::text OR original_run->>'source_id'<>m->>'source_id'
  OR original_run->>'status'<>'partial' OR original_run->>'processing_status'<>'review'
  OR NOT EXISTS(SELECT 1 FROM wholesale_ingest.sources WHERE id=target_source AND source_key=m->>'source_key' AND list_type='tax_delinquent')
  OR EXISTS(SELECT 1 FROM wholesale_ingest.ingest_runs WHERE id=target_run)
  THEN RAISE EXCEPTION 'Historical promotion identity changed'; END IF;
  IF (SELECT count(*) FROM wholesale_ingest.onboarding_promotion_parts WHERE promotion_id=pid)<>(m->>'batches')::int
  THEN RAISE EXCEPTION 'Incomplete private batch staging'; END IF;
  FOR part IN SELECT * FROM wholesale_ingest.onboarding_promotion_parts WHERE promotion_id=pid LOOP
   IF part.source_payload IS DISTINCT FROM part.target_payload OR jsonb_array_length(part.source_payload)<>1
   OR part.entity<>'batch:'||lpad(part.source_payload->0->>'batch_index',4,'0')
   OR part.source_payload->0->>'run_id'<>target_run::text
   OR part.source_payload->0->'payload'->>'run_id'<>target_run::text
   OR part.source_payload->0->'payload'->>'source_key'<>m->>'source_key'
   THEN RAISE EXCEPTION 'Batch identity or payload changed'; END IF;
  END LOOP;
  SELECT md5(jsonb_agg(v ORDER BY v::text)::text) INTO actual_hash
  FROM wholesale_ingest.onboarding_promotion_parts p CROSS JOIN LATERAL jsonb_array_elements(p.source_payload) v WHERE p.promotion_id=pid;
  IF actual_hash IS DISTINCT FROM m->>'payloads_checksum' THEN RAISE EXCEPTION 'Original payload checksum mismatch'; END IF;
  INSERT INTO wholesale_ingest.ingest_runs SELECT * FROM jsonb_populate_record(NULL::wholesale_ingest.ingest_runs,original_run||jsonb_build_object('source_id',target_source));
  INSERT INTO wholesale_ingest.raw_payloads
  SELECT r.* FROM wholesale_ingest.onboarding_promotion_parts p
  CROSS JOIN LATERAL jsonb_populate_recordset(NULL::wholesale_ingest.raw_payloads,p.target_payload) r WHERE p.promotion_id=pid;
  INSERT INTO wholesale_ingest.records(run_id,batch_index,ordinal,source_record_id,record,review_reason)
  SELECT p.run_id,p.batch_index,(v.ordinality-1)::int,v.value->>'source_record_id',v.value,
   CASE WHEN nullif(btrim(v.value->>'parcel_id'),'') IS NOT NULL OR
    (nullif(btrim(v.value->>'property_address'),'') IS NOT NULL AND nullif(btrim(v.value->>'city'),'') IS NOT NULL AND nullif(btrim(v.value->>'zip'),'') IS NOT NULL)
    THEN 'verify_county_property_evidence' ELSE 'missing_property_identity' END
  FROM wholesale_ingest.raw_payloads p CROSS JOIN LATERAL jsonb_array_elements(p.payload->'records') WITH ORDINALITY v WHERE p.run_id=target_run;
  SELECT md5(jsonb_agg(to_jsonb(r) ORDER BY to_jsonb(r)::text)::text) INTO actual_hash FROM wholesale_ingest.records r WHERE r.run_id=target_run;
  IF actual_hash IS DISTINCT FROM m->>'records_checksum' THEN RAISE EXCEPTION 'Original record/review checksum mismatch'; END IF;
  SELECT md5(jsonb_agg(to_jsonb(p) ORDER BY to_jsonb(p)::text)::text) INTO actual_hash FROM wholesale_ingest.raw_payloads p WHERE p.run_id=target_run;
  IF actual_hash IS DISTINCT FROM m->>'payloads_checksum' THEN RAISE EXCEPTION 'Transferred payload checksum mismatch'; END IF;
  IF (SELECT count(*) FROM wholesale_ingest.records WHERE run_id=target_run AND resolved_at IS NULL AND property_id IS NULL)<>(m->>'records')::int
  OR EXISTS(SELECT 1 FROM wholesale_ingest.jobs WHERE run_id=target_run)
  OR EXISTS(SELECT 1 FROM wholesale_ingest.distress_signals WHERE first_run_id=target_run OR last_run_id=target_run)
  THEN RAISE EXCEPTION 'Unverified snapshot must remain review-only'; END IF;
  review_task:=md5('tax-historical-review:'||pid::text)::uuid;
  INSERT INTO public.tasks(id,title,description,status,priority,type,assigned_to,due_date)
  VALUES(review_task,'Review historical '||CASE WHEN m->>'source_key' LIKE '%dallas%' THEN 'Dallas' ELSE 'Collin' END||' tax inventory',
   (m->>'records')||' original historical tax candidates preserved. Verify property identity and current tax balance with official county evidence before qualifying any lead. No tracing or outreach is authorized.',
   'pending','high','follow_up',owner_id,now());
  UPDATE wholesale_ingest.onboarding_promotions SET state='complete',completed_at=now(),
   result=jsonb_build_object('historical_records',(m->>'records')::int,'batches',(m->>'batches')::int,'unresolved',(m->>'records')::int,
    'new_leads',0,'review_task_id',review_task,'dispatch',false,'outreach_authorized',false)
   WHERE id=pid;
  promoted:=promoted+1;
 END LOOP;
 IF (SELECT count(*) FROM public.leads)<>baseline_leads OR (SELECT count(*) FROM wholesale_ingest.properties)<>baseline_properties
 OR (SELECT count(*) FROM public.tasks)<>baseline_tasks+promoted OR (SELECT count(*) FROM wholesale_ingest.skip_trace_requests)<>baseline_traces
 OR (SELECT md5(coalesce(string_agg(row_to_json(e)::text,'' ORDER BY e.id),'')) FROM public.sms_events e) IS DISTINCT FROM baseline_sms
 THEN RAISE EXCEPTION 'Unexpected CRM, tracing or SMS change'; END IF;
END $promotion$;
COMMIT;
SELECT id,state,result,completed_at FROM wholesale_ingest.onboarding_promotions
WHERE id IN('bcb76f65-ceaa-48fb-9ee5-33e010b29d38','79bf66e3-155f-4345-82a1-1a22de9e1500');
