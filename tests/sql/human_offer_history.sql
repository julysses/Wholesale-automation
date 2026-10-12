BEGIN;
DO $$
DECLARE actor uuid; lead uuid:=gen_random_uuid(); draft uuid:=gen_random_uuid(); approval uuid:=gen_random_uuid();
 revoke_id uuid:=gen_random_uuid(); v jsonb; terms jsonb;
BEGIN
 SELECT id INTO actor FROM public.profiles WHERE status='approved' AND role='admin' LIMIT 1;
 IF actor IS NULL THEN RAISE EXCEPTION 'QA requires an approved admin'; END IF;
 INSERT INTO public.leads(id,property_address,city) VALUES(lead,'SYNTHETIC OFFER REVIEW ROLLBACK QA','Dallas');
 terms:=jsonb_build_object('price','123456.78','closing_date','2099-12-31','expires_at','2099-10-01T00:00:00Z',
   'recipient','synthetic@example.invalid','channel','email','conditions','Synthetic rollback test only; no seller contact');
 v:=public.record_offer_review(draft,lead,actor,0,'draft',draft,terms);
 IF (v#>>'{current,version}')::int<>1 OR (v#>>'{current,approved}')::boolean THEN RAISE EXCEPTION 'Draft failed'; END IF;
 v:=public.record_offer_review(approval,lead,actor,1,'approve',draft,NULL);
 IF NOT (v#>>'{current,approved}')::boolean OR (v#>>'{current,outbound_enabled}')::boolean THEN RAISE EXCEPTION 'Approval failed'; END IF;
 v:=public.record_offer_review(revoke_id,lead,actor,2,'revoke',draft,NULL);
 IF (v#>>'{current,approved}')::boolean THEN RAISE EXCEPTION 'Revocation failed'; END IF;
 v:=public.record_offer_review(approval,lead,actor,1,'approve',draft,NULL);
 IF NOT (v->>'replayed')::boolean OR (v#>>'{current,approved}')::boolean THEN RAISE EXCEPTION 'Replay restored approval'; END IF;
 v:=public.record_offer_review(gen_random_uuid(),lead,actor,1,'approve',draft,NULL);
 IF NOT (v->>'conflict')::boolean THEN RAISE EXCEPTION 'Stale version accepted'; END IF;
 v:=public.offer_review_history(lead,actor,NULL);
 IF jsonb_array_length(v->'events')<>3 OR v#>>'{events,0,action}'<>'revoke'
 OR (v#>>'{events,0,operator_id}')::uuid<>actor OR v->>'next_before' IS NOT NULL
 THEN RAISE EXCEPTION 'Audit history lost revocation identity'; END IF;
 v:=public.offer_review_history(lead,actor,1);
 IF jsonb_array_length(v->'events')<>1 OR v#>>'{events,0,action}'<>'draft'
 THEN RAISE EXCEPTION 'History cursor failed'; END IF;
 IF has_function_privilege('anon','public.offer_review_history(uuid,uuid,integer)','execute')
 OR has_function_privilege('authenticated','public.offer_review_history(uuid,uuid,integer)','execute')
 OR NOT has_function_privilege('service_role','public.offer_review_history(uuid,uuid,integer)','execute')
 THEN RAISE EXCEPTION 'History permissions unsafe'; END IF;
 IF has_function_privilege('authenticated' ,'public.record_offer_review(uuid,uuid,uuid,integer,text,uuid,jsonb)','execute')
 OR has_function_privilege('anon','public.offer_review_snapshot(uuid,uuid)','execute')
 OR has_table_privilege('service_role','offer_review.events','UPDATE')
 OR has_table_privilege('service_role','offer_review.events','DELETE') THEN RAISE EXCEPTION 'Offer permissions unsafe'; END IF;
END $$;
ROLLBACK;
SELECT 'offer history rollback passed' AS result;
