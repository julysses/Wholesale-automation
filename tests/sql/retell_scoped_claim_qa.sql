-- Synthetic fixtures, exact-ID claims only; no general drain or provider request.
BEGIN;
DO $$
DECLARE l uuid:=gen_random_uuid(); s uuid:=gen_random_uuid(); j uuid:=gen_random_uuid();
 other_l uuid:=gen_random_uuid(); other_s uuid:=gen_random_uuid(); other_j uuid:=gen_random_uuid();
 p text:='+12145550196'; n int; before_jobs text; before_sms text;
BEGIN
 IF (SELECT enabled FROM private.retell_sms_scheduler WHERE singleton) IS DISTINCT FROM false
 OR EXISTS(SELECT 1 FROM cron.job WHERE jobname='wholesaleos-retell-form-sms' AND active)
 THEN RAISE EXCEPTION 'QA requires disabled scheduler'; END IF;
 IF EXISTS(SELECT 1 FROM public.sms_events WHERE phone_number IN (p,'+12145550197'))
 OR EXISTS(SELECT 1 FROM public.retell_form_sms_jobs WHERE phone_number IN (p,'+12145550197'))
 THEN RAISE EXCEPTION 'Synthetic QA phones already have history'; END IF;
 SELECT md5(coalesce(string_agg(row_to_json(r)::text,'' ORDER BY id),'')) INTO before_jobs FROM public.retell_form_sms_jobs r;
 SELECT md5(coalesce(string_agg(row_to_json(r)::text,'' ORDER BY id),'')) INTO before_sms FROM public.sms_events r;
 INSERT INTO public.leads(id,property_address,city,owner_phone_1,dnc,ai_calling_paused)
 VALUES(l,'SYNTHETIC SCOPED SMS ROLLBACK QA','Dallas',p,false,false),
       (other_l,'SYNTHETIC UNRELATED EXPIRED SMS QA','Dallas','+12145550197',false,false);
 INSERT INTO public.lead_form_submissions(id,lead_id,raw_answers) VALUES(s,l,'{}'),(other_s,other_l,'{}');
 INSERT INTO public.retell_form_sms_jobs(id,lead_id,submission_id,phone_number,due_at,expires_at)
 VALUES(j,l,s,p,now()+interval '1 minute',now()+interval '15 minutes'),
       (other_j,other_l,other_s,'+12145550197',now()-interval '1 day',now()-interval '23 hours');
 SELECT count(*) INTO n FROM public.claim_retell_form_sms_matching(10,j);
 IF n<>0 THEN RAISE EXCEPTION 'Premature scoped claim'; END IF;
 SELECT count(*) INTO n FROM public.claim_retell_form_sms_matching(10,gen_random_uuid());
 IF n<>0 THEN RAISE EXCEPTION 'Missing target claimed another job'; END IF;
 UPDATE public.retell_form_sms_jobs SET due_at=now()-interval '1 second' WHERE id=j;
 SELECT count(*) INTO n FROM public.claim_retell_form_sms_matching(10,j);
 IF n<>1 OR NOT EXISTS(SELECT 1 FROM public.sms_events WHERE id=j AND provider='retell' AND status='submitting') THEN RAISE EXCEPTION 'Scoped claim or shared ledger failed'; END IF;
 SELECT count(*) INTO n FROM public.claim_retell_form_sms_matching(10,j);
 IF n<>0 THEN RAISE EXCEPTION 'Duplicate scoped claim'; END IF;
 IF (SELECT status FROM public.retell_form_sms_jobs WHERE id=other_j)<>'scheduled'
 OR EXISTS(SELECT 1 FROM public.sms_events WHERE id=other_j) THEN RAISE EXCEPTION 'Scoped test touched unrelated expired job'; END IF;
 IF public.outreach_recipient_limits(p)->>'blocker'<>'unresolved_attempt' THEN RAISE EXCEPTION 'Shared contact limit missing'; END IF;
 IF (SELECT md5(coalesce(string_agg(row_to_json(r)::text,'' ORDER BY id),'')) FROM public.retell_form_sms_jobs r WHERE id NOT IN(j,other_j)) IS DISTINCT FROM before_jobs
 OR (SELECT md5(coalesce(string_agg(row_to_json(r)::text,'' ORDER BY id),'')) FROM public.sms_events r WHERE id<>j) IS DISTINCT FROM before_sms
 THEN RAISE EXCEPTION 'Existing production history changed'; END IF;
 IF has_function_privilege('anon','public.claim_retell_form_sms_matching(integer,uuid)','EXECUTE')
 OR has_function_privilege('authenticated','public.claim_retell_form_sms_matching(integer,uuid)','EXECUTE')
 OR NOT has_function_privilege('service_role','public.claim_retell_form_sms_matching(integer,uuid)','EXECUTE')
 OR (SELECT prosecdef FROM pg_proc WHERE oid='public.claim_retell_form_sms_matching(integer,uuid)'::regprocedure)
 THEN RAISE EXCEPTION 'Unexpected scoped claim access'; END IF;
END $$;
ROLLBACK;
SELECT 'Scoped claim, missing target, future job, replay, unrelated expiry, shared ledger, existing-history preservation and access checks passed; rolled back' AS result;
