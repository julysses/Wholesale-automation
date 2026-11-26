-- No provider calls; every synthetic record is rolled back.
BEGIN;
DO $$
DECLARE e uuid:=gen_random_uuid(); l uuid:=gen_random_uuid(); sub uuid:=gen_random_uuid(); j uuid:=gen_random_uuid();
BEGIN
 INSERT INTO public.sms_events(id,provider,direction,status,created_at)
 VALUES(e,'retell','outbound','undelivered',now()-interval '20 minutes');
 IF NOT EXISTS(SELECT 1 FROM public.launch_monitor_findings() WHERE category='sms' AND reference=e) THEN RAISE EXCEPTION 'Retell failure invisible'; END IF;
 UPDATE public.sms_events SET status='accepted',created_at=now()-interval '25 hours' WHERE id=e;
 IF NOT EXISTS(SELECT 1 FROM public.launch_monitor_findings() WHERE category='sms' AND reference=e) THEN RAISE EXCEPTION 'Unconfirmed delivery invisible'; END IF;
 UPDATE public.sms_events SET status='delivered' WHERE id=e;
 IF EXISTS(SELECT 1 FROM public.launch_monitor_findings() WHERE reference=e) THEN RAISE EXCEPTION 'Delivered message falsely flagged'; END IF;
 INSERT INTO public.leads(id,property_address,city) VALUES(l,'SYNTHETIC MONITOR ROLLBACK QA','Dallas');
 INSERT INTO public.lead_form_submissions(id,lead_id,raw_answers) VALUES(sub,l,'{}');
 INSERT INTO public.retell_form_sms_jobs(id,lead_id,submission_id,phone_number,due_at,expires_at,status) VALUES(j,l,sub,'+12145550196',now()-interval '20 minutes',now()-interval '5 minutes','review');
 IF NOT EXISTS(SELECT 1 FROM public.launch_monitor_findings() WHERE category='form_sms' AND reference=j) THEN RAISE EXCEPTION 'Review queue invisible'; END IF;
 UPDATE public.retell_form_sms_jobs SET status='scheduled' WHERE id=j;
 IF NOT EXISTS(SELECT 1 FROM public.launch_monitor_findings() WHERE category='form_sms' AND reference=j) THEN RAISE EXCEPTION 'Overdue queue invisible'; END IF;
 UPDATE public.retell_form_sms_jobs SET status='stopped' WHERE id=j;
 IF EXISTS(SELECT 1 FROM public.launch_monitor_findings() WHERE category='form_sms' AND reference=j) THEN RAISE EXCEPTION 'Stopped queue falsely flagged'; END IF;
 IF has_function_privilege('anon','public.launch_monitor_findings()','EXECUTE') OR has_function_privilege('authenticated','public.launch_monitor_findings()','EXECUTE') THEN RAISE EXCEPTION 'Monitor exposed to browser'; END IF;
END $$;
ROLLBACK;
SELECT 'Retell failure, missing delivery evidence, delivered exclusion and access checks passed; rolled back' AS result;
