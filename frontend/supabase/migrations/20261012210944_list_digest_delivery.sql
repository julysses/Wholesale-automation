BEGIN;
ALTER TABLE wholesale_ingest.daily_digests
 ADD COLUMN message_id uuid UNIQUE, ADD COLUMN recipient text,
 ADD COLUMN delivery_summary jsonb, ADD COLUMN reserved_at timestamptz,
 ADD COLUMN alert_task_id uuid REFERENCES public.tasks;

CREATE FUNCTION public.reserve_list_digest(p_day date,p_recipient text,p_message uuid) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE d wholesale_ingest.daily_digests; mail text:=lower(trim(p_recipient));
BEGIN
 IF p_day IS DISTINCT FROM (now() AT TIME ZONE 'America/Chicago')::date THEN RAISE EXCEPTION 'Only current-day digests may be sent'; END IF;
 IF p_message IS NULL OR mail IS NULL OR length(mail)>320 OR mail!~'^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$' THEN RAISE EXCEPTION 'Valid message and recipient required'; END IF;
 SELECT * INTO d FROM wholesale_ingest.daily_digests WHERE day=p_day FOR UPDATE;
 IF d.day IS NULL OR d.summary IS NULL THEN RAISE EXCEPTION 'Generate digest before reserving delivery'; END IF;
 IF d.message_id IS NOT NULL AND (d.message_id<>p_message OR d.recipient<>mail) THEN RAISE EXCEPTION 'Existing digest reservation is immutable'; END IF;
 IF d.message_id IS NULL THEN
  UPDATE wholesale_ingest.daily_digests SET message_id=p_message,recipient=mail,delivery_summary=summary,
   reserved_at=now(),status='reserved' WHERE day=p_day RETURNING * INTO d;
 END IF;
 RETURN jsonb_build_object('day',d.day,'message_id',d.message_id,'recipient',d.recipient,
 'summary',d.delivery_summary,'send_allowed',d.status IN ('reserved','generated') AND NOT EXISTS(SELECT 1 FROM public.email_messages WHERE id=d.message_id));
END; $$;

CREATE FUNCTION public.reconcile_list_digests() RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE d wholesale_ingest.daily_digests; m public.email_messages; delivered timestamptz; adverse boolean;
 owner_id uuid; task uuid; deadline timestamptz; outcome text; err text;
BEGIN
 IF NOT pg_try_advisory_xact_lock(hashtextextended('wholesaleos:list-digest-reconcile',0)) THEN RETURN jsonb_build_object('busy',true); END IF;
 SELECT p.id INTO owner_id FROM public.app_settings a JOIN public.profiles p ON p.id::text=a.value
 WHERE a.key='lead_owner_user_id' AND p.status='approved' LIMIT 1;
 FOR d IN SELECT * FROM wholesale_ingest.daily_digests WHERE day<=(now() AT TIME ZONE 'America/Chicago')::date
 AND day>=(now() AT TIME ZONE 'America/Chicago')::date-7 FOR UPDATE
 LOOP
  SELECT * INTO m FROM public.email_messages WHERE id=d.message_id AND recipient=d.recipient AND provider='sendgrid';
  SELECT coalesce(bool_or(event IN ('bounce','dropped','spamreport','unsubscribe','group_unsubscribe')),false)
  INTO adverse FROM public.email_delivery_events
  WHERE message_id=m.id AND recipient=d.recipient AND event IN ('delivered','bounce','dropped','spamreport','unsubscribe','group_unsubscribe');
  -- Only a matching delivered event is evidence of delivery; other event timestamps are not.
  SELECT min(occurred_at) INTO delivered FROM public.email_delivery_events WHERE message_id=m.id AND recipient=d.recipient AND event='delivered';
  deadline:=(d.day+time '07:30') AT TIME ZONE 'America/Chicago';
  outcome:=CASE WHEN adverse THEN 'review' WHEN delivered IS NOT NULL THEN 'delivered'
    WHEN m.status='accepted' THEN 'accepted' WHEN m.id IS NOT NULL THEN 'review' ELSE d.status END;
  err:=CASE WHEN adverse THEN 'provider_failure_or_suppression' WHEN m.id IS NOT NULL AND m.status<>'accepted' AND delivered IS NULL THEN 'uncertain_email_attempt' ELSE NULL END;
  IF now()>=deadline AND delivered IS NULL THEN outcome:='review';err:=coalesce(err,'delivery_unconfirmed_by_deadline'); END IF;
  UPDATE wholesale_ingest.daily_digests SET status=outcome,error_code=err,
   accepted_at=CASE WHEN m.status='accepted' OR delivered IS NOT NULL THEN coalesce(accepted_at,now()) ELSE accepted_at END,
   delivered_at=coalesce(delivered_at,delivered) WHERE day=d.day;
  IF outcome='review' AND owner_id IS NOT NULL AND d.alert_task_id IS NULL THEN
   task:=gen_random_uuid();
   INSERT INTO public.tasks(id,title,description,status,priority,type,assigned_to,due_date)
   VALUES(task,'Daily digest delivery needs review',d.day||': '||err||'. Inspect the saved email receipt. Do not resend an uncertain attempt.','pending','high','follow_up',owner_id,now());
   UPDATE wholesale_ingest.daily_digests SET alert_task_id=task WHERE day=d.day;
  END IF;
 END LOOP;
 RETURN jsonb_build_object('digests',(SELECT coalesce(jsonb_agg(jsonb_build_object('day',day,'message_id',message_id,'status',status,'accepted_at',accepted_at,'delivered_at',delivered_at,'error_code',error_code,'on_time',CASE WHEN delivered_at IS NULL THEN NULL ELSE delivered_at<=(day+time '07:30') AT TIME ZONE 'America/Chicago' END) ORDER BY day DESC),'[]') FROM wholesale_ingest.daily_digests WHERE day>=(now() AT TIME ZONE 'America/Chicago')::date-7));
END; $$;
REVOKE ALL ON FUNCTION public.reserve_list_digest(date,text,uuid),public.reconcile_list_digests() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.reserve_list_digest(date,text,uuid),public.reconcile_list_digests() TO service_role;
COMMIT;
