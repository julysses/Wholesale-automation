-- Receipt supervision only: does not collect, order traces, send messages or purge data.
BEGIN;
CREATE TABLE wholesale_ingest.bulk_supervision (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 checked_at timestamptz NOT NULL, successful_at timestamptz,
 attempts bigint NOT NULL DEFAULT 0, state text NOT NULL CHECK(state IN ('healthy','blocked')),
 reason text, summary jsonb NOT NULL DEFAULT '{}', task_id uuid REFERENCES public.tasks(id)
);
ALTER TABLE wholesale_ingest.bulk_supervision ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON wholesale_ingest.bulk_supervision FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON wholesale_ingest.bulk_supervision TO service_role;
CREATE POLICY service_only ON wholesale_ingest.bulk_supervision TO service_role USING(true) WITH CHECK(true);

CREATE FUNCTION wholesale_ingest.supervise_bulk_pipeline() RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE result jsonb; reason text; owner_id uuid; task uuid; stamp timestamptz:=now();
BEGIN
 IF NOT pg_try_advisory_xact_lock(hashtextextended('bulk-supervision-v1',0)) THEN
  RETURN jsonb_build_object('busy',true);
 END IF;
 -- Hold expiry-bearing tables through the guard and scan. The legacy scan contains
 -- retention deletes; this scheduler must never reach those with expired records.
 LOCK TABLE wholesale_ingest.raw_payloads,wholesale_ingest.contacts IN SHARE ROW EXCLUSIVE MODE;
 IF EXISTS(SELECT 1 FROM wholesale_ingest.raw_payloads WHERE expires_at<=stamp)
 OR EXISTS(SELECT 1 FROM wholesale_ingest.contacts WHERE expires_at<=stamp) THEN
  reason:='retention_review_required';
 ELSE
  BEGIN
   result:=public.scan_list_pipeline();
   IF result->>'busy'='true' THEN RETURN result; END IF;
   IF result IS NULL OR result->>'owner_configured' IS DISTINCT FROM 'true' THEN
    reason:='owner_not_configured';
   END IF;
  EXCEPTION WHEN OTHERS THEN
   -- Subtransaction rolls back partial scan changes; no raw error/PII in task text.
   reason:='scan_error_'||SQLSTATE;
  END;
 END IF;
 SELECT id INTO owner_id FROM public.profiles WHERE status='approved'
 AND id::text=(SELECT value FROM public.app_settings WHERE key='lead_owner_user_id' LIMIT 1);
 SELECT task_id INTO task FROM wholesale_ingest.bulk_supervision WHERE singleton;
 IF reason IS NOT NULL AND owner_id IS NOT NULL THEN
  IF task IS NULL THEN
   task:=gen_random_uuid();
   INSERT INTO public.tasks(id,title,description,status,priority,type,assigned_to,due_date)
   VALUES(task,'Bulk workflow needs attention',reason,'pending','high','follow_up',owner_id,stamp);
  ELSE
   UPDATE public.tasks SET description=reason,status='pending',assigned_to=owner_id WHERE id=task;
  END IF;
 END IF;
 INSERT INTO wholesale_ingest.bulk_supervision(singleton,checked_at,successful_at,attempts,state,reason,summary,task_id)
 VALUES(true,stamp,CASE WHEN reason IS NULL THEN stamp END,1,CASE WHEN reason IS NULL THEN 'healthy' ELSE 'blocked' END,
 reason,coalesce(result,'{}'),task)
 ON CONFLICT(singleton) DO UPDATE SET checked_at=excluded.checked_at,
 successful_at=coalesce(excluded.successful_at,bulk_supervision.successful_at),attempts=bulk_supervision.attempts+1,
 state=excluded.state,reason=excluded.reason,summary=excluded.summary,task_id=excluded.task_id;
 RETURN jsonb_build_object('supervision',CASE WHEN reason IS NULL THEN 'healthy' ELSE 'blocked' END,
 'reason',reason,'checked_at',stamp,'collection_executed',false,'provider_ordered',false,'outreach_sent',false);
END $$;
REVOKE ALL ON FUNCTION wholesale_ingest.supervise_bulk_pipeline() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION wholesale_ingest.supervise_bulk_pipeline() TO service_role;
COMMIT;
