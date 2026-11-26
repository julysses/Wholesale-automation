-- Historical Dallas review inventory, staged privately from the recorded run.
-- Execute only after exact production rollback acceptance. No active jobs copied.
BEGIN;
SET LOCAL lock_timeout='10s';
SET LOCAL statement_timeout='90s';
DO $promotion$
DECLARE
 pid uuid:='864bcbf3-e3dd-4fca-be7f-0b05ec97035f';
 owner_id uuid:='89f3b3f6-5a88-4b79-b3f4-461e0cd626a2';
 target_source uuid:='ca93231d-301e-4041-9e12-124717104319';
 target_run uuid:='db1c2221-ed79-4ece-bf12-386a84d59477';
 saved wholesale_ingest.onboarding_promotions; part record; table_name text; missing boolean;
 review jsonb; association jsonb; replay jsonb; baseline_leads bigint;
 baseline_properties bigint; baseline_traces bigint; baseline_sms text;
 review_task uuid:=md5('dallas-historical-review:'||pid::text)::uuid;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('onboarding-promotion:'||pid::text,0));
 SELECT * INTO STRICT saved FROM wholesale_ingest.onboarding_promotions WHERE id=pid FOR UPDATE;
 IF saved.state='complete' THEN RETURN; END IF;
 IF saved.source_project<>'tbhwxgfzbiaqjurghntj' OR saved.operator_id<>owner_id
 OR saved.manifest->>'run_id'<>target_run::text
 OR saved.manifest->>'source_key'<>'tx-dallas-pre_foreclosure'
 THEN RAISE EXCEPTION 'Promotion identity mismatch'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=owner_id AND role='admin' AND status='approved')
 OR NOT EXISTS(SELECT 1 FROM public.app_settings WHERE key='lead_owner_user_id' AND value=owner_id::text)
 THEN RAISE EXCEPTION 'Approved owner changed'; END IF;
 IF EXISTS(SELECT 1 FROM wholesale_ingest.sources WHERE enabled)
 OR EXISTS(SELECT 1 FROM wholesale_ingest.settings WHERE outreach_enabled OR daily_trace_cap_cents<>0)
 OR EXISTS(SELECT 1 FROM private.retell_sms_scheduler WHERE enabled)
 THEN RAISE EXCEPTION 'Collection, spending and sending must stay paused'; END IF;
 IF NOT EXISTS(SELECT 1 FROM wholesale_ingest.sources s WHERE s.id=target_source AND s.source_key='tx-dallas-pre_foreclosure' AND s.county='Dallas')
 OR EXISTS(SELECT 1 FROM wholesale_ingest.ingest_runs i WHERE i.id=target_run)
 THEN RAISE EXCEPTION 'Source mapping or target run changed'; END IF;
 IF (SELECT count(*) FROM wholesale_ingest.onboarding_promotion_parts WHERE promotion_id=pid)<>8
 THEN RAISE EXCEPTION 'Incomplete private staging'; END IF;
 FOR part IN SELECT * FROM wholesale_ingest.onboarding_promotion_parts WHERE promotion_id=pid LOOP
  IF part.entity='property_review' THEN CONTINUE; END IF;
  IF saved.manifest->'source_hashes'->>part.entity IS NULL OR
   (SELECT md5(coalesce(jsonb_agg(v ORDER BY v::text),'[]')::text) FROM jsonb_array_elements(part.source_payload) v)
    IS DISTINCT FROM saved.manifest->'source_hashes'->>part.entity
  THEN RAISE EXCEPTION 'Source checksum mismatch: %',part.entity; END IF;
  IF jsonb_array_length(part.source_payload)<>(saved.manifest->'counts'->>part.entity)::int OR
   part.target_payload IS DISTINCT FROM
   (SELECT jsonb_agg(CASE WHEN v ? 'source_id' THEN v||jsonb_build_object('source_id',target_source) ELSE v END ORDER BY n)
    FROM jsonb_array_elements(part.source_payload) WITH ORDINALITY a(v,n))
  THEN RAISE EXCEPTION 'Only source ID mapping is allowed: %',part.entity; END IF;
 END LOOP;
 SELECT count(*) INTO baseline_leads FROM public.leads;
 SELECT count(*) INTO baseline_properties FROM wholesale_ingest.properties;
 SELECT count(*) INTO baseline_traces FROM wholesale_ingest.skip_trace_requests;
 SELECT md5(coalesce(string_agg(row_to_json(e)::text,'' ORDER BY e.id),'')) INTO baseline_sms FROM public.sms_events e;
 FOREACH table_name IN ARRAY ARRAY['wholesale_ingest.ingest_runs','wholesale_ingest.raw_payloads',
  'wholesale_ingest.foreclosure_first_seen','wholesale_ingest.records','wholesale_ingest.foreclosure_captures',
  'wholesale_ingest.foreclosure_extractions','wholesale_ingest.foreclosure_appraisal_batches'] LOOP
  EXECUTE format('INSERT INTO %s SELECT * FROM jsonb_populate_recordset(NULL::%s,$1)',table_name,table_name)
   USING (SELECT target_payload FROM wholesale_ingest.onboarding_promotion_parts WHERE promotion_id=pid AND onboarding_promotion_parts.entity=table_name);
  EXECUTE format('SELECT EXISTS(SELECT 1 FROM jsonb_array_elements($1) v WHERE NOT EXISTS(SELECT 1 FROM %s a WHERE to_jsonb(a)=v))',table_name)
   INTO STRICT missing USING (SELECT target_payload FROM wholesale_ingest.onboarding_promotion_parts WHERE promotion_id=pid AND onboarding_promotion_parts.entity=table_name);
  IF missing THEN RAISE EXCEPTION 'Transferred row mismatch: %',table_name; END IF;
 END LOOP;
 SELECT source_payload->0 INTO review FROM wholesale_ingest.onboarding_promotion_parts WHERE promotion_id=pid AND onboarding_promotion_parts.entity='property_review';
 IF review->>'source_fingerprint'<>'125a96faa96ce79f2824b753d3e35c6a'
 OR review->'identity'->>'parcel_id'<>'38000500510030200'
 THEN RAISE EXCEPTION 'Reviewed property changed'; END IF;
 association:=public.resolve_reviewed_list_record(target_run,0,41,owner_id,'Dallas',
  'https://www.dallascad.org/AcctDetailRes.aspx?ID=38000500510030200',NULL,false,review);
 IF association->>'new_lead' IS DISTINCT FROM 'true' OR association->>'outreach_authorized' IS DISTINCT FROM 'false'
 THEN RAISE EXCEPTION 'Unexpected property association'; END IF;
 replay:=public.resolve_reviewed_list_record(target_run,0,41,owner_id,'Dallas',
  'https://www.dallascad.org/AcctDetailRes.aspx?ID=38000500510030200',NULL,false,review);
 IF replay->>'replayed' IS DISTINCT FROM 'true' OR replay->>'lead_id' IS DISTINCT FROM association->>'lead_id'
 THEN RAISE EXCEPTION 'Review replay failed'; END IF;
 IF (SELECT count(*) FROM public.leads)<>baseline_leads+1
 OR (SELECT count(*) FROM wholesale_ingest.properties)<>baseline_properties+1
 OR NOT EXISTS(SELECT 1 FROM public.leads l WHERE l.id=(association->>'lead_id')::uuid
  AND l.assigned_to=owner_id AND NOT l.sms_sequence_active AND NOT l.email_sequence_active)
 OR (SELECT count(*) FROM public.tasks t WHERE t.lead_id=(association->>'lead_id')::uuid
  AND t.assigned_to=owner_id AND t.type='follow_up' AND t.status='pending')<>1
 THEN RAISE EXCEPTION 'Lead, owner or follow-up invariant failed'; END IF;
 IF (SELECT count(*) FROM wholesale_ingest.records r WHERE r.run_id=target_run AND r.resolved_at IS NULL)<>489
 OR EXISTS(SELECT 1 FROM wholesale_ingest.distress_signals s WHERE s.first_run_id=target_run AND s.active)
 OR EXISTS(SELECT 1 FROM wholesale_ingest.jobs j WHERE j.run_id=target_run)
 THEN RAISE EXCEPTION 'Review holds or inactive-work invariant failed'; END IF;
 INSERT INTO public.tasks(id,title,description,status,priority,type,assigned_to,due_date)
 VALUES(review_task,'Review historical Dallas foreclosure inventory',
  '490 historical index records preserved with original evidence; 489 still need property review. One property has an inactive signal and its own follow-up. Current sale status is unverified. No tracing or outreach is authorized.',
  'pending','high','follow_up',owner_id,now());
 IF (SELECT count(*) FROM wholesale_ingest.skip_trace_requests)<>baseline_traces OR
  (SELECT md5(coalesce(string_agg(row_to_json(e)::text,'' ORDER BY e.id),'')) FROM public.sms_events e) IS DISTINCT FROM baseline_sms
 THEN RAISE EXCEPTION 'Unexpected tracing or SMS change'; END IF;
 UPDATE wholesale_ingest.onboarding_promotions SET state='complete',completed_at=now(),
  result=jsonb_build_object('historical_records',490,'property_reviewed',1,'unresolved',489,
   'lead_id',association->>'lead_id','property_id',association->>'property_id','review_task_id',review_task,
   'capture_receipts',1,'extraction_receipts',5,'appraisal_receipts',1,'dispatch',false,'outreach_authorized',false)
 WHERE id=pid;
END $promotion$;
COMMIT;
SELECT id,state,result,completed_at FROM wholesale_ingest.onboarding_promotions WHERE id='864bcbf3-e3dd-4fca-be7f-0b05ec97035f';
