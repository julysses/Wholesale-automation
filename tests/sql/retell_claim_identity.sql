BEGIN;
DO $$
DECLARE actor uuid; lead uuid:=gen_random_uuid(); reference uuid:=gen_random_uuid(); v jsonb; saved public.retell_call_requests;
BEGIN
 SELECT id INTO actor FROM public.profiles WHERE status='approved' AND role='admin' LIMIT 1;
 IF actor IS NULL THEN RAISE EXCEPTION 'Approved admin needed for rollback QA'; END IF;
 INSERT INTO public.leads(id,property_address,city,dnc,ai_calling_paused,owner_phone_1)
 VALUES(lead,'SYNTHETIC RETELL IDENTITY ROLLBACK QA','Dallas',false,false,'+12145550198');
 v:=public.claim_retell_call_versioned(reference,lead,'+12145550198',actor,'agent_synthetic',7,'+14698049920');
 IF v->>'claimed'<>'true' THEN RAISE EXCEPTION 'Synthetic claim failed: %',v; END IF;
 SELECT * INTO saved FROM public.retell_call_requests WHERE id=reference;
 IF saved.requested_agent_id<>'agent_synthetic' OR saved.requested_agent_version<>7
 OR saved.requested_from_number<>'+14698049920' THEN RAISE EXCEPTION 'Identity not saved'; END IF;
 BEGIN
  UPDATE public.retell_call_requests SET requested_agent_version=8 WHERE id=reference;
  RAISE EXCEPTION 'FAIL identity mutation accepted';
 EXCEPTION WHEN OTHERS THEN
  IF SQLERRM NOT LIKE '%initiation identity is immutable%' THEN RAISE; END IF;
 END;
 UPDATE public.retell_call_requests SET status='unknown' WHERE id=reference;
 v:=public.claim_retell_call_versioned(reference,lead,'+12145550198',actor,'agent_other',8,'+14698049920');
 IF v->>'claimed'<>'false' THEN RAISE EXCEPTION 'Replay replaced identity'; END IF;
 IF has_function_privilege('service_role','public.claim_retell_call(uuid,uuid,text,uuid)','execute')
 OR has_function_privilege('anon','public.claim_retell_call_versioned(uuid,uuid,text,uuid,text,integer,text)','execute')
 OR has_function_privilege('authenticated','public.claim_retell_call_versioned(uuid,uuid,text,uuid,text,integer,text)','execute')
 THEN RAISE EXCEPTION 'Unexpected initiation permissions'; END IF;
END $$;
ROLLBACK;
SELECT 'Retell identity rollback passed' AS result;
