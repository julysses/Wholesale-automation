-- Synthetic property, no phones and no external actions. Always rolled back.
BEGIN;
DO $$
DECLARE l uuid:=gen_random_uuid(); p uuid:=gen_random_uuid(); owner_id uuid; result jsonb;
BEGIN
 SELECT pr.id INTO owner_id FROM public.profiles pr JOIN public.app_settings a ON a.value=pr.id::text
 WHERE a.key='lead_owner_user_id' AND pr.status='approved';
 IF owner_id IS NULL THEN RAISE EXCEPTION 'Approved owner missing'; END IF;
 IF EXISTS(SELECT 1 FROM wholesale_ingest.sources WHERE enabled)
 OR EXISTS(SELECT 1 FROM wholesale_ingest.settings WHERE outreach_enabled OR daily_trace_cap_cents<>0)
 OR (SELECT enabled FROM private.retell_sms_scheduler WHERE singleton)
 THEN RAISE EXCEPTION 'Acceptance requires inactive collection, spending and SMS'; END IF;
 INSERT INTO public.leads(id,property_address,city,state,status,dnc,ai_calling_paused,sms_sequence_active,email_sequence_active)
 VALUES(l,'SYNTHETIC COUNTY ONBOARDING ROLLBACK QA','Dallas','TX','new',true,true,false,false);
 INSERT INTO wholesale_ingest.properties(id,state,county,address_std,city,lead_id)
 VALUES(p,'TX','Dallas','SYNTHETIC COUNTY ONBOARDING ROLLBACK QA','Dallas',l);
 IF (SELECT assigned_to FROM public.leads WHERE id=l) IS DISTINCT FROM owner_id
 OR NOT EXISTS(SELECT 1 FROM public.tasks WHERE lead_id=l AND assigned_to=owner_id AND status='pending')
 THEN RAISE EXCEPTION 'Lead or task owner missing'; END IF;
 IF NOT EXISTS(SELECT 1 FROM wholesale_ingest.property_alert_events WHERE property_id=p AND notified_at IS NOT NULL)
 THEN RAISE EXCEPTION 'County notification not saved'; END IF;
 UPDATE public.tasks SET status='completed' WHERE lead_id=l;
 UPDATE wholesale_ingest.properties SET lead_id=l WHERE id=p;
 IF (SELECT count(*) FROM public.tasks WHERE lead_id=l)<>1 OR NOT EXISTS(SELECT 1 FROM public.tasks WHERE lead_id=l AND status='completed')
 THEN RAISE EXCEPTION 'Replay duplicated or reopened follow-up'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.leads WHERE id=l AND dnc AND ai_calling_paused AND NOT sms_sequence_active AND NOT email_sequence_active)
 THEN RAISE EXCEPTION 'Suppression changed'; END IF;
 PERFORM public.list_pipeline_snapshot(current_date,0);
 PERFORM public.propstream_handoff_snapshot(owner_id,0);
 PERFORM public.foreclosure_capture_status(owner_id);
 IF has_table_privilege('authenticated','wholesale_ingest.contacts','SELECT')
 OR has_function_privilege('authenticated','public.list_pipeline_snapshot(date,integer)','EXECUTE')
 THEN RAISE EXCEPTION 'Private pipeline exposed to browser'; END IF;
END $$;
ROLLBACK;
SELECT 'Production onboarding ownership, follow-up, replay, notification, suppression, snapshots and access checks passed; rolled back' AS result;
