-- A verified county lead needs an accountable owner and its own durable review task.
-- Runs in the same transaction as property association. Never sends outreach.
CREATE OR REPLACE FUNCTION wholesale_ingest.queue_property_alert() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE owner_id uuid; task_id uuid;
BEGIN
 IF TG_OP='UPDATE' AND OLD.lead_id IS NOT NULL THEN RETURN NEW; END IF;
 IF NEW.lead_id IS NOT NULL THEN
  SELECT assigned_to INTO owner_id FROM public.leads WHERE id=NEW.lead_id FOR UPDATE;
  IF owner_id IS NULL THEN
   SELECT p.id INTO owner_id FROM public.profiles p JOIN public.app_settings a ON a.value=p.id::text
   WHERE a.key='lead_owner_user_id' AND p.status='approved' LIMIT 1;
  END IF;
  IF owner_id IS NULL OR NOT EXISTS(SELECT 1 FROM public.profiles WHERE id=owner_id AND status='approved')
  THEN RAISE EXCEPTION 'Approved county intake owner required'; END IF;
  UPDATE public.leads SET assigned_to=owner_id WHERE id=NEW.lead_id AND assigned_to IS NULL;
  task_id:=md5('county-intake:'||NEW.lead_id::text)::uuid;
  INSERT INTO public.tasks(id,title,description,status,priority,type,lead_id,assigned_to,due_date)
  VALUES(task_id,'Review newly onboarded county property',
   'Review verified property evidence, existing trace results and current contact permissions in Daily Lists. This task does not authorize outreach.',
   'pending','high','follow_up',NEW.lead_id,owner_id,now()) ON CONFLICT(id) DO NOTHING;
  INSERT INTO wholesale_ingest.property_alert_events(property_id,lead_id) VALUES(NEW.id,NEW.lead_id) ON CONFLICT DO NOTHING;
  PERFORM wholesale_ingest.publish_property_alerts();
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION wholesale_ingest.queue_property_alert() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION wholesale_ingest.queue_property_alert() TO service_role;
