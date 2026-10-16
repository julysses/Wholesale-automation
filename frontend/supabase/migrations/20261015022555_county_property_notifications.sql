-- New CRM property alerts, not raw-record alerts or tracing/outreach authorization.
BEGIN;
CREATE TABLE wholesale_ingest.property_alert_events (
 property_id uuid PRIMARY KEY REFERENCES wholesale_ingest.properties(id),
 lead_id uuid NOT NULL REFERENCES public.leads(id),
 added_at timestamptz NOT NULL DEFAULT now(), notified_at timestamptz
);
CREATE TABLE wholesale_ingest.property_alert_days (
 day date PRIMARY KEY, notification_id uuid NOT NULL UNIQUE REFERENCES public.app_notifications(id),
 task_id uuid NOT NULL UNIQUE REFERENCES public.tasks(id)
);
ALTER TABLE wholesale_ingest.property_alert_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE wholesale_ingest.property_alert_days ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.property_alert_events,wholesale_ingest.property_alert_days FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON wholesale_ingest.property_alert_events,wholesale_ingest.property_alert_days TO service_role;
CREATE POLICY service_only ON wholesale_ingest.property_alert_events TO service_role USING(true) WITH CHECK(true);
CREATE POLICY service_only ON wholesale_ingest.property_alert_days TO service_role USING(true) WITH CHECK(true);
CREATE FUNCTION wholesale_ingest.publish_property_alerts() RETURNS integer
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE owner_id uuid; d date; total integer; notification uuid; task uuid; added integer:=0; affected integer;
BEGIN
 PERFORM pg_advisory_xact_lock(hashtextextended('county-property-alerts',0));
 SELECT p.id INTO owner_id FROM public.profiles p JOIN public.app_settings a ON a.value=p.id::text
 WHERE a.key='lead_owner_user_id' AND p.status='approved' LIMIT 1;
 IF owner_id IS NULL THEN RETURN 0; END IF;
 FOR d IN SELECT DISTINCT (added_at AT TIME ZONE 'America/Chicago')::date
 FROM wholesale_ingest.property_alert_events WHERE notified_at IS NULL LOOP
  SELECT count(*) INTO total FROM wholesale_ingest.property_alert_events
  WHERE (added_at AT TIME ZONE 'America/Chicago')::date=d;
  SELECT notification_id,task_id INTO notification,task FROM wholesale_ingest.property_alert_days WHERE day=d;
  IF NOT FOUND THEN
   notification:=gen_random_uuid();task:=gen_random_uuid();
   INSERT INTO public.app_notifications(id,recipient_id,type,title,body,action_url,action_label,metadata)
   VALUES(notification,owner_id,'pipeline_step','New county properties added',
    total||' new CRM properties added on '||d||'. Review verification and bulk skip-trace readiness.',
    '/daily-lists','Review new properties',jsonb_build_object('day',d,'property_count',total,'outreach_authorized',false));
   INSERT INTO public.tasks(id,title,description,status,priority,type,assigned_to,due_date)
   VALUES(task,'High priority: new county properties',total||' new CRM properties added on '||d||'. Open Daily Lists for verification and bulk PropStream preparation. Contact returns do not clear calls or SMS.',
    'pending','high','follow_up',owner_id,now());
   INSERT INTO wholesale_ingest.property_alert_days VALUES(d,notification,task);
  ELSE
   UPDATE public.app_notifications SET recipient_id=owner_id,body=total||' new CRM properties added on '||d||'. Review verification and bulk skip-trace readiness.',
    metadata=jsonb_build_object('day',d,'property_count',total,'outreach_authorized',false),read=false,read_at=NULL WHERE id=notification;
   UPDATE public.tasks SET status='pending',assigned_to=owner_id,description=total||' new CRM properties added on '||d||'. Open Daily Lists for verification and bulk PropStream preparation. Contact returns do not clear calls or SMS.' WHERE id=task;
  END IF;
  UPDATE wholesale_ingest.property_alert_events SET notified_at=now()
  WHERE notified_at IS NULL AND (added_at AT TIME ZONE 'America/Chicago')::date=d;
  GET DIAGNOSTICS affected=ROW_COUNT;
  added:=added+affected;
 END LOOP;
 RETURN added;
END $$;
CREATE FUNCTION wholesale_ingest.queue_property_alert() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF TG_OP='UPDATE' AND OLD.lead_id IS NOT NULL THEN RETURN NEW; END IF;
 IF NEW.lead_id IS NOT NULL THEN
  INSERT INTO wholesale_ingest.property_alert_events(property_id,lead_id) VALUES(NEW.id,NEW.lead_id) ON CONFLICT DO NOTHING;
  PERFORM wholesale_ingest.publish_property_alerts();
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER county_property_added AFTER INSERT OR UPDATE OF lead_id ON wholesale_ingest.properties
FOR EACH ROW EXECUTE FUNCTION wholesale_ingest.queue_property_alert();
REVOKE ALL ON FUNCTION wholesale_ingest.publish_property_alerts(),wholesale_ingest.queue_property_alert() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION wholesale_ingest.publish_property_alerts(),wholesale_ingest.queue_property_alert() TO service_role;
COMMIT;
