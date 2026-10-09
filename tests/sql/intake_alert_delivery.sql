BEGIN;
DO $$
DECLARE ref uuid:=gen_random_uuid(); manual_ref uuid:=gen_random_uuid(); form uuid; payload jsonb; r jsonb;
 lead uuid; alert uuid; manual_lead uuid; manual_alert uuid; claim uuid:=gen_random_uuid(); other_claim uuid:=gen_random_uuid();
 original_owner text;
BEGIN
 SELECT id INTO form FROM public.lead_form_configs WHERE slug='the-jays-dallas';
 SELECT to_jsonb(l) INTO payload FROM public.leads l ORDER BY id LIMIT 1;
 payload:=payload||jsonb_build_object('property_address','Rollback-only alert QA','owner_email','internal-qa@example.invalid',
  'owner_phone_1','','internal_notes','Rollback-only intake alert verification','status','new','source','web_form','inbound_channel','web_form','ai_calling_paused',true);
 PERFORM public.reserve_form_submission(ref,jsonb_build_object('form_id',form,'raw_answers',jsonb_build_object('first_name','Rollback alert QA')),jsonb_build_object('fixture',ref));
 r:=public.finalize_form_submission(ref,payload); lead:=(r->>'lead_id')::uuid; alert:=(r->>'notification_id')::uuid;
 IF (SELECT processing_status FROM public.lead_form_submissions WHERE id=ref)<>'processed'
  OR (SELECT count(*) FROM public.tasks WHERE id=ref AND lead_id=lead)<>1
  OR (SELECT count(*) FROM public.app_notifications WHERE id=alert AND lead_id=lead AND metadata->>'delivery_state'='pending')<>1 THEN
  RAISE EXCEPTION 'Receipt acknowledgement lacks atomic lead, task and pending alert'; END IF;
 -- Simulate process termination after finalization, before delivery starts.
 r:=public.finalize_form_submission(ref,payload);
 IF r->>'created'<>'false' OR (r->>'lead_id')::uuid<>lead OR (r->>'notification_id')::uuid<>alert THEN RAISE EXCEPTION 'Finalization duplicated records'; END IF;
 UPDATE public.app_notifications SET created_at=now()-interval '10 minutes' WHERE id=alert;
 IF NOT EXISTS(SELECT 1 FROM public.launch_monitor_findings() WHERE category='intake_alert' AND reference=alert) THEN RAISE EXCEPTION 'Pending alert invisible to monitoring'; END IF;
 PERFORM public.scan_launch_monitor(); PERFORM public.scan_launch_monitor();
 IF (SELECT count(*) FROM public.launch_monitor_incidents WHERE category='intake_alert' AND reference=alert AND resolved_at IS NULL)<>1 THEN RAISE EXCEPTION 'Recovery review missing or duplicated'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.tasks t JOIN public.launch_monitor_incidents i ON t.id=i.id WHERE i.reference=alert AND t.assigned_to IS NOT NULL) THEN RAISE EXCEPTION 'Stalled alert lacks assigned task'; END IF;
 r:=public.claim_intake_notification(lead,claim,'{"title":"Rollback claim QA","body":"No provider transmission"}');
 IF r->>'claimed'<>'true' OR (r->>'claim_id')::uuid<>claim THEN RAISE EXCEPTION 'Pending delivery not claimed'; END IF;
 r:=public.claim_intake_notification(lead,other_claim,'{"title":"Rollback claim QA","body":"No provider transmission"}');
 IF r->>'claimed'<>'false' THEN RAISE EXCEPTION 'Second worker claimed an attempted delivery'; END IF;
 -- Lost claim acknowledgement / interrupted provider result stays parked, never re-leased.
 UPDATE public.app_notifications SET metadata=metadata||jsonb_build_object('claimed_at',now()-interval '10 minutes') WHERE id=alert;
 IF NOT EXISTS(SELECT 1 FROM public.launch_monitor_findings() WHERE category='intake_alert' AND reference=alert) THEN RAISE EXCEPTION 'Parked attempt not monitored'; END IF;
 r:=public.finish_intake_notification(lead,other_claim,'{"owner_email":"accepted","seller_sms":"no_consent_or_phone"}','Wrong claim');
 IF r->>'finished'<>'false' THEN RAISE EXCEPTION 'Another worker overwrote delivery evidence'; END IF;
 r:=public.finish_intake_notification(lead,claim,'{"owner_email":"accepted","seller_sms":"no_consent_or_phone"}','Provider accepted; delivery unconfirmed');
 IF r->>'finished'<>'true' OR r->>'delivery_state'<>'completed' THEN RAISE EXCEPTION 'Confirmed outcomes not retained'; END IF;
 r:=public.claim_intake_notification(lead,other_claim,'{"title":"Rollback claim QA","body":"No provider transmission"}');
 IF r->>'claimed'<>'false' THEN RAISE EXCEPTION 'Completed delivery reclaimed'; END IF;
 PERFORM public.scan_launch_monitor();
 IF EXISTS(SELECT 1 FROM public.launch_monitor_incidents WHERE category='intake_alert' AND reference=alert AND resolved_at IS NULL) THEN RAISE EXCEPTION 'Resolved outcome still escalated'; END IF;
 -- Previously unresolved legacy records may have sent: never infer that sending is safe.
 UPDATE public.app_notifications SET metadata='{"owner_email":"unresolved"}' WHERE id=alert;
 r:=public.claim_intake_notification(lead,other_claim,'{"title":"Rollback claim QA","body":"No provider transmission"}');
 IF r->>'claimed'<>'false' OR NOT EXISTS(SELECT 1 FROM public.launch_monitor_findings() WHERE category='intake_alert' AND reference=alert) THEN RAISE EXCEPTION 'Legacy uncertainty did not remain manual review'; END IF;
 PERFORM public.reserve_form_submission(manual_ref,jsonb_build_object('form_id',form,'raw_answers',jsonb_build_object('first_name','Manual review QA')),jsonb_build_object('fixture',manual_ref));
 r:=public.finalize_form_submission(manual_ref,payload||'{"_intake_recovery_only":true}'::jsonb);
 manual_lead:=(r->>'lead_id')::uuid; manual_alert:=(r->>'notification_id')::uuid;
 r:=public.claim_intake_notification(manual_lead,other_claim,'{"title":"Rollback claim QA","body":"No provider transmission"}');
 IF r->>'claimed'<>'false' OR (SELECT metadata->>'delivery_state' FROM public.app_notifications WHERE id=manual_alert)<>'review' THEN RAISE EXCEPTION 'Admin recovery enabled provider replay'; END IF;
 IF has_function_privilege('anon','public.claim_intake_notification(uuid,uuid,jsonb)','EXECUTE')
  OR has_function_privilege('authenticated','public.claim_intake_notification(uuid,uuid,jsonb)','EXECUTE')
  OR has_function_privilege('authenticated','public.finish_intake_notification(uuid,uuid,jsonb,text)','EXECUTE')
  OR has_column_privilege('authenticated','public.app_notifications','metadata','UPDATE') THEN RAISE EXCEPTION 'Browser can alter delivery claims'; END IF;
END $$;
ROLLBACK;
SELECT count(*) AS retained_fixtures FROM public.leads WHERE internal_notes='Rollback-only intake alert verification';
