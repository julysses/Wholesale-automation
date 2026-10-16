-- Private staging and durable promotion receipts. Not an ingestion or dispatch endpoint.
CREATE TABLE wholesale_ingest.onboarding_promotions(
 id uuid PRIMARY KEY, source_project text NOT NULL, scope text NOT NULL,
 operator_id uuid NOT NULL REFERENCES public.profiles(id), created_at timestamptz NOT NULL DEFAULT now(),
 state text NOT NULL DEFAULT 'staged' CHECK(state IN ('staged','complete')),
 manifest jsonb NOT NULL, result jsonb, completed_at timestamptz
);
CREATE TABLE wholesale_ingest.onboarding_promotion_parts(
 promotion_id uuid NOT NULL REFERENCES wholesale_ingest.onboarding_promotions(id),
 entity text NOT NULL, source_payload jsonb NOT NULL, target_payload jsonb NOT NULL,
 PRIMARY KEY(promotion_id,entity),
 CHECK(jsonb_typeof(source_payload)='array' AND jsonb_typeof(target_payload)='array')
);
ALTER TABLE wholesale_ingest.onboarding_promotions ENABLE ROW LEVEL SECURITY;
ALTER TABLE wholesale_ingest.onboarding_promotion_parts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.onboarding_promotions,wholesale_ingest.onboarding_promotion_parts FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON wholesale_ingest.onboarding_promotions TO service_role;
GRANT SELECT,INSERT ON wholesale_ingest.onboarding_promotion_parts TO service_role;

-- Reuse an already assigned follow-up (including completed historical work) during association.
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
  SELECT id INTO task_id FROM public.tasks WHERE lead_id=NEW.lead_id AND type='follow_up'
   AND assigned_to=owner_id ORDER BY id LIMIT 1;
  IF task_id IS NULL THEN
   task_id:=md5('county-intake:'||NEW.lead_id::text)::uuid;
   INSERT INTO public.tasks(id,title,description,status,priority,type,lead_id,assigned_to,due_date)
   VALUES(task_id,'Review newly onboarded county property',
    'Review verified property evidence, existing trace results and current contact permissions in Daily Lists. This task does not authorize outreach.',
    'pending','high','follow_up',NEW.lead_id,owner_id,now()) ON CONFLICT(id) DO NOTHING;
  END IF;
  INSERT INTO wholesale_ingest.property_alert_events(property_id,lead_id) VALUES(NEW.id,NEW.lead_id) ON CONFLICT DO NOTHING;
  PERFORM wholesale_ingest.publish_property_alerts();
 END IF;
 RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION wholesale_ingest.queue_property_alert() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION wholesale_ingest.queue_property_alert() TO service_role;
