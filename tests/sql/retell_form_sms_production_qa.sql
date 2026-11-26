-- Synthetic records only. Rollback always; scheduler must be disabled.
BEGIN;
DO $$
DECLARE l uuid:=gen_random_uuid(); s uuid:=gen_random_uuid(); j uuid:=gen_random_uuid();
 p text:='+12145550196'; n int; result jsonb;
BEGIN
 IF (SELECT enabled FROM private.retell_sms_scheduler WHERE singleton) IS DISTINCT FROM false
 OR EXISTS(SELECT 1 FROM cron.job WHERE jobname='wholesaleos-retell-form-sms' AND active)
 OR EXISTS(SELECT 1 FROM public.retell_form_sms_jobs WHERE status='scheduled' AND due_at<=now())
 THEN RAISE EXCEPTION 'QA requires disabled scheduler and no due real jobs'; END IF;
 INSERT INTO public.leads(id,property_address,city,owner_phone_1,dnc,ai_calling_paused)
 VALUES(l,'SYNTHETIC SMS QUEUE ROLLBACK QA','Dallas',p,false,false);
 INSERT INTO public.lead_form_submissions(id,lead_id,raw_answers) VALUES(s,l,'{}');
 INSERT INTO public.retell_form_sms_jobs(id,lead_id,submission_id,phone_number,due_at,expires_at)
 VALUES(j,l,s,p,now()+interval '60 seconds',now()+interval '15 minutes');
 SELECT count(*) INTO n FROM public.claim_retell_form_sms(3);
 IF n<>0 THEN RAISE EXCEPTION 'Premature dispatch claim'; END IF;
 UPDATE public.retell_form_sms_jobs SET due_at=now()-interval '1 second' WHERE id=j;
 SELECT count(*) INTO n FROM public.claim_retell_form_sms(3);
 IF n<>1 OR NOT EXISTS(SELECT 1 FROM public.sms_events WHERE id=j AND provider='retell' AND status='submitting') THEN RAISE EXCEPTION 'Due claim or shared ledger failed'; END IF;
 SELECT count(*) INTO n FROM public.claim_retell_form_sms(3);
 IF n<>0 THEN RAISE EXCEPTION 'Duplicate claim'; END IF;
 result:=public.claim_twilio_sms(gen_random_uuid(),l,p,'QA never sent');
 IF result->>'claimed'<>'false' THEN RAISE EXCEPTION 'Twilio bypassed Retell claim'; END IF;
 IF public.outreach_recipient_limits(p)->>'blocker'<>'unresolved_attempt' THEN RAISE EXCEPTION 'Shared contact limit missing'; END IF;
 -- Exercise expiry and suppression without sending anything.
 UPDATE public.retell_form_sms_jobs SET status='scheduled',expires_at=now()-interval '1 second' WHERE id=j;
 SELECT count(*) INTO n FROM public.claim_retell_form_sms(3);
 IF n<>0 OR (SELECT status FROM public.retell_form_sms_jobs WHERE id=j)<>'stopped' THEN RAISE EXCEPTION 'Expiry failed'; END IF;
 UPDATE public.retell_form_sms_jobs SET status='scheduled',expires_at=now()+interval '15 minutes' WHERE id=j;
 UPDATE public.leads SET dnc=true WHERE id=l;
 SELECT count(*) INTO n FROM public.claim_retell_form_sms(3);
 IF n<>0 OR (SELECT status FROM public.retell_form_sms_jobs WHERE id=j)<>'stopped' THEN RAISE EXCEPTION 'Suppression failed'; END IF;
 IF has_table_privilege('anon','public.retell_form_sms_jobs','INSERT') OR has_function_privilege('authenticated','public.claim_retell_form_sms(integer)','EXECUTE') THEN RAISE EXCEPTION 'Unexpected queue access'; END IF;
END $$;
ROLLBACK;
SELECT 'Timing, single claim, shared ledger, cooldown, expiry, suppression, and queue access passed; rolled back' AS result;
