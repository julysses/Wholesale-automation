BEGIN;
DO $$
DECLARE ref uuid:=gen_random_uuid(); next_ref uuid:=gen_random_uuid(); form uuid; submission jsonb; manifest jsonb;
 r jsonb; first_lead uuid; lead_payload jsonb; old_stamp text;
BEGIN
 SELECT id INTO form FROM public.lead_form_configs WHERE active ORDER BY id LIMIT 1;
 submission:=jsonb_build_object('form_id',form,'raw_answers',jsonb_build_object('first_name','Rollback QA','email','internal-qa@example.invalid','_sms_consent',jsonb_build_object('accepted',false,'recorded_at','first timestamp')),
   'utm_source','rollback-verification','ip_address','127.0.0.1');
 manifest:=jsonb_build_object('form_id',form,'answers',jsonb_build_object('first_name','Rollback QA','email','internal-qa@example.invalid'),'consent',jsonb_build_object('accepted',false));
 r:=public.reserve_form_submission(ref,submission,manifest);
 IF r->>'status'<>'created' OR r->>'submission_id'<>ref::text THEN RAISE EXCEPTION 'Original receipt not confirmed'; END IF;
 submission:=jsonb_set(jsonb_set(submission,'{raw_answers,_sms_consent,recorded_at}','"retry timestamp"'),'{ip_address}','"127.0.0.2"');
 r:=public.reserve_form_submission(ref,submission,manifest);
 IF r->>'status'<>'replayed' THEN RAISE EXCEPTION 'Same inquiry not replayed'; END IF;
 SELECT raw_answers#>>'{_sms_consent,recorded_at}' INTO old_stamp FROM public.lead_form_submissions WHERE id=ref;
 IF old_stamp<>'first timestamp' THEN RAISE EXCEPTION 'Replay rewrote original consent evidence'; END IF;
 r:=public.reserve_form_submission(ref,submission,jsonb_set(manifest,'{answers,first_name}','"Changed"'));
 IF r->>'status'<>'conflict' THEN RAISE EXCEPTION 'Changed manifest accepted'; END IF;
 SELECT to_jsonb(l) INTO lead_payload FROM public.reportable_leads l ORDER BY id LIMIT 1;
 lead_payload:=lead_payload||jsonb_build_object('property_address','Rollback-only intake reference QA','owner_email','internal-qa@example.invalid','owner_phone_1','','internal_notes','Rollback-only inquiry reference verification','status','new','source','web_form','inbound_channel','web_form','ai_calling_paused',true);
 r:=public.finalize_form_submission(ref,lead_payload);
 first_lead:=(r->>'lead_id')::uuid;
 IF r->>'created'<>'true' THEN RAISE EXCEPTION 'Lead not created'; END IF;
 r:=public.finalize_form_submission(ref,lead_payload);
 IF r->>'created'<>'false' OR (r->>'lead_id')::uuid<>first_lead THEN RAISE EXCEPTION 'Finalization replay duplicated lead'; END IF;
 IF (SELECT count(*) FROM public.tasks WHERE id=ref)<>1 OR (SELECT count(*) FROM public.leads WHERE form_submission_id=ref)<>1 THEN RAISE EXCEPTION 'Receipt task/lead multiplicity'; END IF;
 r:=public.reserve_form_submission(next_ref,submission,manifest);
 IF r->>'status'<>'created' THEN RAISE EXCEPTION 'Different inquiry was merged by contact'; END IF;
 r:=public.finalize_form_submission(next_ref,lead_payload);
 IF (r->>'lead_id')::uuid=first_lead THEN RAISE EXCEPTION 'Separate inquiry merged'; END IF;
 IF has_function_privilege('authenticated','public.reserve_form_submission(uuid,jsonb,jsonb)','EXECUTE')
 OR has_function_privilege('anon','public.reserve_form_submission(uuid,jsonb,jsonb)','EXECUTE') THEN RAISE EXCEPTION 'Browser can reserve receipts directly'; END IF;
END $$;
ROLLBACK;
SELECT count(*) AS retained_fixtures FROM public.leads WHERE internal_notes='Rollback-only inquiry reference verification';

