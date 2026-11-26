BEGIN;
DO $$
DECLARE
 a uuid:=gen_random_uuid(); b uuid:=gen_random_uuid(); e uuid:=gen_random_uuid();
 s uuid:=gen_random_uuid(); late uuid:=gen_random_uuid(); v jsonb;
 phone text:='+12145550197';
 payload jsonb:=jsonb_build_object('MessageSid','SM'||repeat('e',32),'From','+12145550197','Body','Tomorrow afternoon works');
BEGIN
 INSERT INTO public.leads(id,property_address,city,dnc,owner_phone_1) VALUES
  (a,'SYNTHETIC SMS ROUTING ROLLBACK QA A','Dallas',false,phone),
  (b,'SYNTHETIC SMS ROUTING ROLLBACK QA B','Dallas',false,'(214) 555-0197');
 v:=public.record_twilio_event(e,'inbound',payload);
 IF v->>'saved'<>'true' OR v->>'suppressed'<>'false' THEN RAISE EXCEPTION 'Reply receipt failed: %',v; END IF;
 IF (SELECT count(*) FROM public.tasks WHERE id=e AND priority='high' AND status='pending')<>1 THEN RAISE EXCEPTION 'Missing follow-up'; END IF;
 v:=public.record_twilio_event(e,'inbound',payload);
 IF v->>'duplicate'<>'true' THEN RAISE EXCEPTION 'Duplicate not recognized'; END IF;
 INSERT INTO public.tasks(id,lead_id,title,status,type) VALUES
 (gen_random_uuid(),a,'Retell SMS reply: review and follow up','pending','acquisition_review'),
 (gen_random_uuid(),b,'Retell SMS reply: review and follow up','completed','acquisition_review');
 v:=public.record_twilio_event(s,'inbound',jsonb_build_object('MessageSid','SM'||repeat('f',32),'From',phone,'Body','STOP','OptOutType','STOP'));
 IF (SELECT count(*) FROM public.leads WHERE id IN (a,b) AND dnc AND ai_calling_paused AND sms_sequence_active=false)<>2 THEN RAISE EXCEPTION 'Phone-wide STOP failed'; END IF;
 IF EXISTS(SELECT 1 FROM public.tasks WHERE lead_id IN(a,b) AND status='pending') THEN RAISE EXCEPTION 'STOP left pending SMS task'; END IF;
 IF (SELECT count(*) FROM public.tasks WHERE lead_id=b AND status='completed')<>1 THEN RAISE EXCEPTION 'Completed task changed'; END IF;
 v:=public.record_twilio_event(late,'inbound',payload||jsonb_build_object('MessageSid','SM'||repeat('a',32)));
 IF v->>'suppressed'<>'true' OR EXISTS(SELECT 1 FROM public.tasks WHERE id=late) THEN RAISE EXCEPTION 'Late reply reopened followup'; END IF;
 v:=public.record_twilio_event(gen_random_uuid(),'inbound',payload||jsonb_build_object('Body','START','OptOutType','START'));
 IF (SELECT count(*) FROM public.leads WHERE id IN(a,b) AND dnc)<>2 THEN RAISE EXCEPTION 'START cleared suppression'; END IF;
 IF has_function_privilege('anon','public.record_twilio_event(uuid,text,jsonb)','execute')
 OR has_function_privilege('authenticated','public.record_twilio_event(uuid,text,jsonb)','execute') THEN RAISE EXCEPTION 'Unexpected callback access'; END IF;
END $$;
ROLLBACK;
SELECT 'Carrier reply, duplicate, phone-wide STOP, late reply, START, and task preservation passed' AS result;
