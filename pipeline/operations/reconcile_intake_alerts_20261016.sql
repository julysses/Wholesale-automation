-- Exactly two reviewed historical alerts. No provider operations or new work.
BEGIN;
SET LOCAL lock_timeout='10s';
SET LOCAL statement_timeout='60s';
DO $review$
DECLARE item record; n public.app_notifications; f public.lead_form_submissions;
 owner_id uuid:='89f3b3f6-5a88-4b79-b3f4-461e0cd626a2';
 channel_before text; channel_after text; task_count bigint; note text; sms_before text;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('wholesaleos:launch-monitor',0));
 IF EXISTS(SELECT 1 FROM private.retell_sms_scheduler WHERE enabled)
 OR EXISTS(SELECT 1 FROM wholesale_ingest.sources WHERE enabled)
 THEN RAISE EXCEPTION 'Paused controls changed'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=owner_id AND role='admin' AND status='approved')
 THEN RAISE EXCEPTION 'Approved reviewer missing'; END IF;
 SELECT count(*) INTO task_count FROM public.tasks;
 SELECT md5(coalesce(string_agg(row_to_json(e)::text,'' ORDER BY e.id),'')) INTO sms_before FROM public.sms_events e;
 SELECT md5(jsonb_build_object(
  'jobs',(SELECT jsonb_agg(to_jsonb(j) ORDER BY id) FROM public.retell_form_sms_jobs j),
  'dnc',(SELECT jsonb_agg(to_jsonb(d) ORDER BY id) FROM public.dnc_registry d),
  'resub',(SELECT jsonb_agg(to_jsonb(r) ORDER BY stop_event_id) FROM public.sms_resubscription_reviews r))::text) INTO channel_before;
 FOR item IN SELECT * FROM (VALUES
  ('383df308-8cb4-5658-a9a6-5f19ff0ba381'::uuid,'ed786291-3112-4ea4-8fe8-de03e2f7de5b'::uuid,'557529d4-8225-4428-88a8-0791935a046f'::uuid,'50bc5279-2a96-4176-a6b4-adc364313387'::uuid,'dee4dc5c-6bc9-59e3-bfd7-b6c5024caa7c'::uuid,'suppression_at_submission'),
  ('ff6f7996-1261-5e29-b4df-1620b8784deb'::uuid,'0e9372ca-5310-488c-bed9-c538a408ee97'::uuid,'a7b6f49b-f460-4619-a22d-8afe776336d8'::uuid,'fe19ef32-4ad5-475d-95fc-3baf33cea513'::uuid,'46ac04bb-28e0-5fad-aba7-44222e6a183c'::uuid,'later_reviewed_handoff')
 ) v(alert_id,incident_id,submission_id,lead_id,email_id,disposition)
 LOOP
  SELECT * INTO STRICT n FROM public.app_notifications WHERE id=item.alert_id FOR UPDATE;
  IF n.metadata->>'handoff_reconciliation'='verified_historical_hold_20261016' THEN CONTINUE; END IF;
  SELECT * INTO STRICT f FROM public.lead_form_submissions WHERE id=item.submission_id;
  IF n.lead_id IS DISTINCT FROM item.lead_id OR f.lead_id IS DISTINCT FROM item.lead_id
  OR f.processing_status<>'processed' OR n.metadata->>'delivery_state'<>'review'
  OR n.metadata->>'submission_id'<>item.submission_id::text
  OR n.metadata->>'seller_sms'<>'consent_or_suppression_hold'
  OR n.metadata->>'owner_email_message_id'<>item.email_id::text
  OR NOT EXISTS(SELECT 1 FROM public.email_messages m JOIN public.email_delivery_events e
    ON e.message_id=m.id AND e.recipient=m.recipient WHERE m.id=item.email_id AND e.event='delivered')
  OR NOT EXISTS(SELECT 1 FROM public.tasks WHERE id=item.submission_id AND lead_id=item.lead_id AND assigned_to=owner_id AND status='pending')
  THEN RAISE EXCEPTION 'Historical receipt, delivered owner email or assigned follow-up mismatch'; END IF;
  IF item.disposition='suppression_at_submission' THEN
   IF NOT EXISTS(SELECT 1 FROM public.sms_events stop JOIN public.sms_events start
      ON start.phone_number=stop.phone_number
     WHERE stop.id='a412d09e-fe46-513b-b2d8-bfc8f252f259' AND stop.opt_out IS TRUE AND stop.provider='twilio' AND stop.direction='inbound'
     AND start.id='8275990d-ca46-5f67-8082-cf577036ce00' AND start.raw_payload->>'OptOutType'='START'
     AND stop.created_at<f.created_at AND start.created_at>f.created_at
     AND right(regexp_replace(f.raw_answers->>'phone','[^0-9]','','g'),10)=right(stop.phone_number,10))
    OR EXISTS(SELECT 1 FROM public.retell_form_sms_jobs WHERE submission_id=item.submission_id)
   THEN RAISE EXCEPTION 'Expected historical STOP before inquiry and later START not proven'; END IF;
   note:='Reviewed original inquiry: matching carrier STOP preceded submission; START occurred later. Suppression correctly prevented SMS. Owner email delivered and seller follow-up remains pending. No resend or permission change.';
  ELSE
   IF NOT EXISTS(SELECT 1 FROM public.sms_resubscription_reviews r JOIN public.retell_form_sms_jobs j ON j.submission_id=r.submission_id
     JOIN public.sms_events e ON e.id=j.id
     WHERE r.submission_id=item.submission_id AND public.sms_stop_has_reviewed_opt_in(r.stop_event_id)
     AND j.lead_id=item.lead_id AND j.id='e2e9231a-27ae-566f-8e3d-30c6096e5013' AND j.status='review'
     AND j.chat_id='chat_3e830c21a691319298d4d773598' AND e.status='undelivered')
   THEN RAISE EXCEPTION 'Reviewed consent and subsequent carrier failure not proven'; END IF;
   note:='Original intake hold was followed by reviewed START plus fresh consent and a saved Retell handoff. Owner email delivered. Twilio subsequently confirmed SMS undelivered 30007; independent SMS and form-SMS incidents remain open. No resend or delivery-success claim.';
  END IF;
  UPDATE public.app_notifications SET metadata=metadata||jsonb_build_object(
   'delivery_state','completed','handoff_reconciliation','verified_historical_hold_20261016',
   'handoff_reconciled_at',clock_timestamp(),'handoff_review',jsonb_build_object(
     'operator_id',owner_id,'disposition',item.disposition,'note',note,'email_message_id',item.email_id,
     'stop_event_id','a412d09e-fe46-513b-b2d8-bfc8f252f259','start_event_id','8275990d-ca46-5f67-8082-cf577036ce00')),
   body=body||' Reviewed: '||note WHERE id=item.alert_id;
  UPDATE public.tasks SET status='completed',description=description||E'\n\n'||note
   WHERE id=item.incident_id AND lead_id=item.lead_id AND assigned_to=owner_id
   AND title='Review stalled intake_alert processing' AND status='pending';
  IF NOT FOUND THEN RAISE EXCEPTION 'Original monitor task changed'; END IF;
  UPDATE public.app_notifications SET metadata=metadata||jsonb_build_object('resolved_at',clock_timestamp(),'resolution',note),
   body=body||' Resolution: '||note WHERE id=item.incident_id AND metadata->>'launch_monitor'='true';
 END LOOP;
 PERFORM public.scan_launch_monitor();
 IF EXISTS(SELECT 1 FROM public.launch_monitor_incidents WHERE id IN ('ed786291-3112-4ea4-8fe8-de03e2f7de5b','0e9372ca-5310-488c-bed9-c538a408ee97') AND resolved_at IS NULL)
 OR (SELECT count(*) FROM public.launch_monitor_incidents WHERE reference='e2e9231a-27ae-566f-8e3d-30c6096e5013' AND category IN ('sms','form_sms') AND resolved_at IS NULL)<>2
 OR (SELECT count(*) FROM public.tasks)<>task_count
 THEN RAISE EXCEPTION 'Monitor resolution or separate carrier failure state changed'; END IF;
 SELECT md5(jsonb_build_object(
  'jobs',(SELECT jsonb_agg(to_jsonb(j) ORDER BY id) FROM public.retell_form_sms_jobs j),
  'dnc',(SELECT jsonb_agg(to_jsonb(d) ORDER BY id) FROM public.dnc_registry d),
  'resub',(SELECT jsonb_agg(to_jsonb(r) ORDER BY stop_event_id) FROM public.sms_resubscription_reviews r))::text) INTO channel_after;
 IF channel_after IS DISTINCT FROM channel_before OR
  (SELECT md5(coalesce(string_agg(row_to_json(e)::text,'' ORDER BY e.id),'')) FROM public.sms_events e) IS DISTINCT FROM sms_before
 THEN RAISE EXCEPTION 'Channel records changed'; END IF;
END $review$;
COMMIT;
SELECT public.launch_monitor_snapshot() AS monitor;
