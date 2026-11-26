BEGIN;
DO $$
DECLARE stopid uuid := 'a412d09e-fe46-513b-b2d8-bfc8f252f259'; startid uuid := '8275990d-ca46-5f67-8082-cf577036ce00'; subid uuid := 'a7b6f49b-f460-4619-a22d-8afe776336d8'; phone text; lid uuid; jid uuid := gen_random_uuid(); freshstop uuid := gen_random_uuid(); n int;
BEGIN
SELECT phone_number INTO phone FROM public.sms_events WHERE id=stopid;
SELECT lead_id INTO lid FROM public.lead_form_submissions WHERE id=subid;
IF public.sms_stop_has_reviewed_opt_in(stopid) THEN RAISE EXCEPTION 'Unreviewed START must not clear STOP'; END IF;
INSERT INTO public.sms_resubscription_reviews VALUES(stopid,startid,subid,now(),'QA reviewed carrier START and fresh consent; rolled back');
IF NOT public.sms_stop_has_reviewed_opt_in(stopid) THEN RAISE EXCEPTION 'Valid reviewed opt-in rejected'; END IF;
IF (public.intake_phone_status(phone,lid,'')->>'suppressed')::boolean THEN RAISE EXCEPTION 'Reviewed historical STOP still blocks'; END IF;
UPDATE public.sms_resubscription_reviews SET start_event_id=stopid WHERE stop_event_id=stopid;
IF public.sms_stop_has_reviewed_opt_in(stopid) THEN RAISE EXCEPTION 'Invalid START accepted'; END IF;
UPDATE public.sms_resubscription_reviews SET start_event_id=startid WHERE stop_event_id=stopid;
INSERT INTO public.dnc_registry(id,phone_number,reason,source) VALUES(freshstop,phone,'opt_out','twilio');
IF NOT (public.intake_phone_status(phone,lid,'')->>'suppressed')::boolean THEN RAISE EXCEPTION 'New STOP must block'; END IF;
DELETE FROM public.dnc_registry WHERE id=freshstop;
UPDATE public.leads SET dnc=true WHERE id=lid;
IF NOT (public.intake_phone_status(phone,lid,'')->>'suppressed')::boolean THEN RAISE EXCEPTION 'Lead DNC must still block'; END IF;
UPDATE public.leads SET dnc=false WHERE id=lid;
INSERT INTO public.retell_form_sms_jobs(id,lead_id,submission_id,phone_number,due_at,expires_at) VALUES(jid,lid,subid,phone,now()-interval '1 second',now()+interval '1 minute');
SELECT count(*) INTO n FROM public.claim_retell_form_sms(1) WHERE id=jid;
IF n<>1 THEN RAISE EXCEPTION 'Reviewed consented job not claimable'; END IF;
IF has_table_privilege('service_role','public.sms_resubscription_reviews','INSERT') OR has_table_privilege('authenticated','public.sms_resubscription_reviews','SELECT') THEN RAISE EXCEPTION 'Review permissions too broad'; END IF;
END $$;
ROLLBACK;
SELECT 'PASS: unreviewed START blocked; valid review allowed; invalid START, fresh STOP, lead DNC blocked; claim works; restricted access; all rolled back' AS result;
