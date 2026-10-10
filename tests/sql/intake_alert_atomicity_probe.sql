-- ISOLATED TEST DATABASE ONLY. Requires DDL privileges; never run against production.
-- The deliberately raised exception rolls back both the temporary constraint and fixtures.
DO $$
DECLARE ref uuid:=gen_random_uuid(); form uuid; payload jsonb; blocked boolean:=false; failed_constraint text;
BEGIN
 SELECT id INTO form FROM public.lead_form_configs WHERE slug='the-jays-dallas';
 SELECT to_jsonb(l) INTO payload FROM public.leads l ORDER BY id LIMIT 1;
 payload:=payload||jsonb_build_object('property_address','Rollback alert failure QA','owner_email','internal-qa@example.invalid','owner_phone_1','','internal_notes','Rollback alert failure proof','status','new','source','web_form','inbound_channel','web_form','ai_calling_paused',true);
 -- This entire inner block is rolled back through the deliberate final exception.
 BEGIN
  ALTER TABLE public.app_notifications ADD CONSTRAINT codex_isolated_alert_failure CHECK (title <> 'New inquiry — follow-up required') NOT VALID;
  PERFORM public.reserve_form_submission(ref,jsonb_build_object('form_id',form,'raw_answers',jsonb_build_object('first_name','Rollback failure QA')),jsonb_build_object('fixture',ref));
  BEGIN
   PERFORM public.finalize_form_submission(ref,payload);
  EXCEPTION WHEN check_violation THEN
   GET STACKED DIAGNOSTICS failed_constraint=CONSTRAINT_NAME;
   IF failed_constraint <> 'codex_isolated_alert_failure' THEN RAISE; END IF;
   blocked:=true;
  END;
  IF NOT blocked THEN RAISE EXCEPTION 'Test did not block alert persistence'; END IF;
  IF EXISTS(SELECT 1 FROM public.leads WHERE form_submission_id=ref)
  OR EXISTS(SELECT 1 FROM public.tasks WHERE id=ref)
  OR EXISTS(SELECT 1 FROM public.lead_form_submissions WHERE id=ref AND (lead_id IS NOT NULL OR processing_status='processed'))
  THEN RAISE EXCEPTION 'Partial inquiry state survived failed alert persistence'; END IF;
  RAISE EXCEPTION USING ERRCODE='ZX001',MESSAGE='successful proof: rollback fixture and constraint';
 EXCEPTION WHEN SQLSTATE 'ZX001' THEN NULL;
 END;
 IF EXISTS(SELECT 1 FROM pg_constraint WHERE conname='codex_isolated_alert_failure')
 OR EXISTS(SELECT 1 FROM public.lead_form_submissions WHERE id=ref)
 THEN RAISE EXCEPTION 'Failure proof retained test state'; END IF;
END $$;
