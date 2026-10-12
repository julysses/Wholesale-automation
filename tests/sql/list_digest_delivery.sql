-- Isolated rehearsal only; synthetic ledger events are NOT live provider receipts.
BEGIN;
DO $$
DECLARE today date:=(now() AT TIME ZONE 'America/Chicago')::date;
 message uuid:=gen_random_uuid(); receipt jsonb; evidence jsonb;
BEGIN
 ASSERT NOT EXISTS(SELECT 1 FROM wholesale_ingest.daily_digests WHERE day=today), 'Existing rehearsal digest requires separate fixture isolation';
 INSERT INTO wholesale_ingest.daily_digests(day,status,summary) VALUES(today,'generated',jsonb_build_object('day',today,'new_leads',7));
 receipt:=public.reserve_list_digest(today,'synthetic@example.test',message);
 ASSERT (receipt->>'send_allowed')::boolean, 'Initial reservation should permit email claim';
 UPDATE wholesale_ingest.daily_digests SET summary=jsonb_build_object('day',today,'new_leads',99) WHERE day=today;
 receipt:=public.reserve_list_digest(today,'synthetic@example.test',message);
 ASSERT receipt->'summary'->>'new_leads'='7', 'Reservation content changed';
 INSERT INTO public.email_messages(id,recipient,subject,provider,status) VALUES(message,'synthetic@example.test','Synthetic rollback digest','sendgrid','attempting');
 receipt:=public.reserve_list_digest(today,'synthetic@example.test',message);
 ASSERT NOT (receipt->>'send_allowed')::boolean, 'Existing uncertain email may not resend';
 evidence:=public.reconcile_list_digests();
 ASSERT (SELECT delivered_at IS NULL FROM wholesale_ingest.daily_digests WHERE day=today), 'Attempt is not delivery';
 UPDATE public.email_messages SET status='accepted' WHERE id=message;
 evidence:=public.reconcile_list_digests();
 ASSERT (SELECT accepted_at IS NOT NULL AND delivered_at IS NULL FROM wholesale_ingest.daily_digests WHERE day=today), 'Acceptance mistaken for delivery';
 INSERT INTO public.email_delivery_events(event_id,message_id,recipient,event,occurred_at,payload)
 VALUES('synthetic-'||message,message,'synthetic@example.test','delivered',now(),'{}');
 evidence:=public.reconcile_list_digests();
 ASSERT (SELECT status='delivered' AND delivered_at IS NOT NULL FROM wholesale_ingest.daily_digests WHERE day=today), 'Matching delivery not reconciled';
END $$;
ROLLBACK;
