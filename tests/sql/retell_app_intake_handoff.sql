-- Transaction-only QA: no HTTP, provider, worker dispatch or durable test data.
BEGIN;
DO $$
DECLARE ref uuid; form uuid; lead uuid; alert uuid; claim uuid; job uuid;
 payload jsonb; r jsonb; transport text; outcome text; expected_transport text;
 sms_before text;
BEGIN
 IF EXISTS(SELECT 1 FROM private.retell_sms_scheduler WHERE enabled)
  OR EXISTS(SELECT 1 FROM private.retell_app_scheduler WHERE enabled) THEN
  RAISE EXCEPTION 'Paused schedulers required for transaction-only QA'; END IF;
 SELECT md5(coalesce(jsonb_agg(to_jsonb(e) ORDER BY id)::text,'[]')) INTO sms_before FROM public.sms_events e;
 SELECT id INTO STRICT form FROM public.lead_form_configs WHERE slug='the-jays-dallas';
 -- Keep existing schema enum/default compatibility; every fixture is new and rolled back.
 SELECT to_jsonb(l) INTO payload FROM public.leads l ORDER BY id LIMIT 1;
 payload:=payload||jsonb_build_object('property_address','Rollback-only app handoff QA',
  'owner_first_name','Rollback QA','owner_last_name','Not a customer','owner_email','internal-qa@example.invalid',
  'owner_phone_1','+12145550199','internal_notes','Rollback-only app handoff verification',
  'status','new','source','web_form','inbound_channel','web_form','ai_calling_paused',true);
 FOREACH transport IN ARRAY ARRAY['retell_native','app_twilio'] LOOP
  ref:=gen_random_uuid();claim:=gen_random_uuid();job:=gen_random_uuid();
  PERFORM public.reserve_form_submission(ref,jsonb_build_object('form_id',form,
   'raw_answers',jsonb_build_object('first_name','Rollback QA')),jsonb_build_object('fixture',ref));
  r:=public.finalize_form_submission(ref,payload);
  lead:=(r->>'lead_id')::uuid;alert:=(r->>'notification_id')::uuid;
  IF NOT EXISTS(SELECT 1 FROM public.tasks WHERE id=ref AND lead_id=lead AND assigned_to IS NOT NULL)
   THEN RAISE EXCEPTION 'Follow-up assignment missing'; END IF;
  r:=public.claim_intake_notification(lead,claim,'{"title":"Rollback-only handoff QA","body":"No provider transmission"}');
  IF r->>'claimed'<>'true' THEN RAISE EXCEPTION 'Fixture notification claim missing'; END IF;
  r:=public.finish_intake_notification(lead,claim,'{"owner_email":"accepted","seller_sms":"scheduled_app_twilio_60_seconds"}','Missing queue');
  IF r->>'delivery_state'<>'review' THEN RAISE EXCEPTION 'Missing job falsely completed'; END IF;
  INSERT INTO public.retell_form_sms_jobs(id,lead_id,submission_id,phone_number,due_at,expires_at,status,
   delivery_transport,delivery_body,delivery_sender)
  VALUES(job,lead,ref,'+12145550199',now()-interval '1 hour',now()-interval '45 minutes','review',transport,
   CASE WHEN transport='app_twilio' THEN 'Rollback-only, never send' ELSE NULL END,
   CASE WHEN transport='app_twilio' THEN '+14695550100' ELSE NULL END);
  FOREACH outcome IN ARRAY ARRAY['scheduled_retell_60_seconds','scheduled_retell_next_contact_window',
   'existing_retell_native_job','scheduled_app_twilio_60_seconds','scheduled_app_twilio_next_contact_window','existing_app_twilio_job'] LOOP
   UPDATE public.app_notifications SET metadata=metadata||'{"delivery_state":"processing"}'::jsonb WHERE id=alert;
   r:=public.finish_intake_notification(lead,gen_random_uuid(),jsonb_build_object('owner_email','accepted','seller_sms',outcome),'Wrong claimant');
   IF r->>'finished'<>'false' THEN RAISE EXCEPTION 'Wrong claimant accepted'; END IF;
   r:=public.finish_intake_notification(lead,claim,jsonb_build_object('owner_email','accepted','seller_sms',outcome),'Queue handoff only; carrier unconfirmed');
   expected_transport:=CASE WHEN outcome LIKE '%app_twilio%' THEN 'app_twilio' ELSE 'retell_native' END;
   IF r->>'delivery_state'<>CASE WHEN transport=expected_transport THEN 'completed' ELSE 'review' END
    THEN RAISE EXCEPTION 'Transport classification mismatch: % / %',transport,outcome; END IF;
   r:=public.finish_intake_notification(lead,claim,jsonb_build_object('owner_email','accepted','seller_sms',outcome),'Forbidden replay');
   IF r->>'finished'<>'false' THEN RAISE EXCEPTION 'Notification replay allowed'; END IF;
  END LOOP;
  UPDATE public.app_notifications SET metadata=metadata||'{"delivery_state":"processing"}'::jsonb WHERE id=alert;
  r:=public.finish_intake_notification(lead,claim,jsonb_build_object('owner_email','unknown','seller_sms',
   CASE WHEN transport='app_twilio' THEN 'existing_app_twilio_job' ELSE 'existing_retell_native_job' END),'Email unconfirmed');
  IF r->>'delivery_state'<>'review' THEN RAISE EXCEPTION 'Email uncertainty hidden'; END IF;
  IF (SELECT status FROM public.retell_form_sms_jobs WHERE id=job)<>'review'
   OR NOT EXISTS(SELECT 1 FROM public.launch_monitor_findings() WHERE category='form_sms' AND reference=job)
   OR EXISTS(SELECT 1 FROM public.sms_events WHERE id=job) THEN
   RAISE EXCEPTION 'Handoff classification changed channel evidence or monitoring'; END IF;
 END LOOP;
 IF (SELECT md5(coalesce(jsonb_agg(to_jsonb(e) ORDER BY id)::text,'[]')) FROM public.sms_events e) IS DISTINCT FROM sms_before
  THEN RAISE EXCEPTION 'Unexpected SMS mutation'; END IF;
END $$;
ROLLBACK;
SELECT count(*) AS retained_fixture_leads FROM public.leads WHERE internal_notes='Rollback-only app handoff verification';
