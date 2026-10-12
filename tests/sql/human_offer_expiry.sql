-- Rehearsal only. All synthetic data is rolled back. Requires an existing approved admin.
BEGIN;
DO $$
DECLARE actor uuid; l uuid:=gen_random_uuid(); d uuid:=gen_random_uuid(); a uuid:=gen_random_uuid(); v jsonb;
BEGIN
 SELECT id INTO actor FROM public.profiles WHERE role='admin' AND status='approved' LIMIT 1;
 IF actor IS NULL THEN RAISE EXCEPTION 'Missing QA admin'; END IF;
 INSERT INTO public.leads(id,property_address,city) VALUES(l,'SYNTHETIC OFFER EXPIRY ROLLBACK QA','Dallas');
 v:=public.record_offer_review(d,l,actor,0,'draft',d,jsonb_build_object('price','100000','closing_date','2099-12-31','expires_at',clock_timestamp()+interval '500 milliseconds','recipient','synthetic@example.invalid','channel','email','conditions','Synthetic expiry rollback only'));
 v:=public.record_offer_review(a,l,actor,1,'approve',d,NULL);
 IF NOT (v#>>'{current,approved}')::boolean THEN RAISE EXCEPTION 'Before-expiry approval failed'; END IF;
 PERFORM pg_sleep(0.7);
 v:=public.offer_review_snapshot(l,actor);
 IF (v->>'approved')::boolean THEN RAISE EXCEPTION 'Expired approval stayed active'; END IF;
 v:=public.record_offer_review(a,l,actor,1,'approve',d,NULL);
 IF NOT (v->>'replayed')::boolean OR (v#>>'{current,approved}')::boolean THEN RAISE EXCEPTION 'Replay restored expired approval'; END IF;
 v:=public.record_offer_review(gen_random_uuid(),l,actor,2,'approve',d,NULL);
 IF NOT (v->>'expired')::boolean THEN RAISE EXCEPTION 'Expired revision reapproved'; END IF;
END $$;
ROLLBACK;
SELECT 'timed expiry and expired replay passed' AS result;
