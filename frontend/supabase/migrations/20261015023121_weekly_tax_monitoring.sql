-- Weekly tax expectations match the Mac's once-per-week attempts; foreclosure stays daily.
BEGIN;
ALTER TABLE wholesale_ingest.sources ADD COLUMN collection_cadence text NOT NULL DEFAULT 'daily' CHECK(collection_cadence IN ('daily','weekly'));
ALTER TABLE wholesale_ingest.sources ADD COLUMN cadence_effective_on date;
CREATE FUNCTION wholesale_ingest.collection_due_day(cadence text,effective_on date,d date) RETURNS date
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT CASE WHEN cadence='weekly' AND d>=effective_on THEN greatest(date_trunc('week',d::timestamp)::date,effective_on) ELSE d END
$$;
REVOKE ALL ON FUNCTION wholesale_ingest.collection_due_day(text,date,date) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION wholesale_ingest.collection_due_day(text,date,date) TO service_role;
UPDATE wholesale_ingest.sources SET collection_cadence='weekly',cadence_effective_on=(now() AT TIME ZONE 'America/Chicago')::date,schedule_cron='17 6 * * 1',deadline_local='08:00'
WHERE source_key IN ('tx-dallas-tax_delinquent','tx-collin-tax_delinquent');
CREATE OR REPLACE FUNCTION wholesale_ingest.scan_at(p_now timestamptz) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE today date:=(p_now AT TIME ZONE 'America/Chicago')::date;
 owner_id uuid; e record; latest wholesale_ingest.ingest_runs; reason text;
 count_batches int; incident wholesale_ingest.monitor_incidents; summary jsonb;
BEGIN
 IF p_now IS NULL THEN RAISE EXCEPTION 'Scan time required'; END IF;
 IF NOT pg_try_advisory_xact_lock(hashtextextended('wholesaleos:list-monitor',0)) THEN RETURN jsonb_build_object('busy',true); END IF;
 SELECT p.id INTO owner_id FROM public.app_settings a JOIN public.profiles p ON p.id::text=a.value
 WHERE a.key='lead_owner_user_id' AND p.status='approved' LIMIT 1;
 -- Recover up to seven missed daily schedules, only after procedure approval.
 INSERT INTO wholesale_ingest.expected_runs(source_id,day,due_at)
 SELECT s.id,d::date,(d::date+s.deadline_local) AT TIME ZONE s.timezone
 FROM wholesale_ingest.sources s CROSS JOIN generate_series(today-7,today,interval '1 day') d
 WHERE s.enabled AND s.procedure_approved_at IS NOT NULL
 AND d::date >= (s.procedure_approved_at AT TIME ZONE s.timezone)::date
 AND wholesale_ingest.collection_due_day(s.collection_cadence,s.cadence_effective_on,d::date)=d::date
 ON CONFLICT DO NOTHING;

 -- Raw expiry never changes an unresolved run into a successful empty run.
 UPDATE wholesale_ingest.ingest_runs i SET
 processing_status=CASE WHEN i.status<>'success' OR EXISTS(SELECT 1 FROM wholesale_ingest.records r WHERE r.run_id=i.id AND r.resolved_at IS NULL) THEN 'review' ELSE 'completed' END,
 completed_at=CASE WHEN i.status='success' AND NOT EXISTS(SELECT 1 FROM wholesale_ingest.records r WHERE r.run_id=i.id AND r.resolved_at IS NULL) THEN coalesce(i.completed_at,p_now) ELSE NULL END
 WHERE i.processing_status<>'completed'
 AND (SELECT count(*) FROM wholesale_ingest.raw_payloads b WHERE b.run_id=i.id)=i.expected_batches
 AND NOT EXISTS(SELECT 1 FROM wholesale_ingest.raw_payloads b WHERE b.run_id=i.id AND (b.batch_index>=i.expected_batches OR b.purged_at IS NOT NULL));
 UPDATE wholesale_ingest.jobs j SET state=CASE WHEN i.processing_status='completed' THEN 'done' ELSE 'review' END
 FROM wholesale_ingest.ingest_runs i WHERE i.id=j.run_id AND i.processing_status IN ('review','completed') AND j.state='pending';

 FOR e IN SELECT x.*,s.source_key,s.collection_cadence,s.cadence_effective_on FROM wholesale_ingest.expected_runs x
 JOIN wholesale_ingest.sources s ON s.id=x.source_id WHERE s.enabled AND x.day<=today
 AND wholesale_ingest.collection_due_day(s.collection_cadence,s.cadence_effective_on,x.day)=x.day
 LOOP
  SELECT * INTO latest FROM wholesale_ingest.ingest_runs i
   WHERE i.source_id=e.source_id AND wholesale_ingest.collection_due_day(e.collection_cadence,e.cadence_effective_on,i.scheduled_for)=e.day
   ORDER BY i.received_at DESC,i.id DESC LIMIT 1;
  SELECT count(*) INTO count_batches FROM wholesale_ingest.raw_payloads WHERE run_id=latest.id;
  reason:=NULL;
  IF latest.id IS NULL THEN
   IF e.due_at<=p_now THEN reason:='missing'; END IF;
  ELSIF latest.status<>'success' THEN reason:=latest.status;
  ELSIF count_batches<>latest.expected_batches THEN
   IF e.due_at<=p_now THEN reason:='incomplete'; END IF;
  ELSIF latest.processing_status='review' THEN reason:='property_review';
  END IF;
  IF reason IS NOT NULL THEN
   INSERT INTO wholesale_ingest.monitor_incidents(source_id,day,kind,run_id,first_seen_at,last_seen_at)
   VALUES(e.source_id,e.day,reason,latest.id,p_now,p_now)
   ON CONFLICT(source_id,day) DO UPDATE SET kind=excluded.kind,run_id=excluded.run_id,last_seen_at=p_now,resolved_at=NULL
   RETURNING * INTO incident;
   IF owner_id IS NOT NULL AND incident.task_id IS NULL THEN
    incident.task_id:=gen_random_uuid();
    INSERT INTO public.tasks(id,title,description,status,priority,type,assigned_to,due_date)
    VALUES(incident.task_id,'Daily list needs review',e.source_key||' ('||e.day||'): '||reason||'. Check collection and delivery; never infer zero records from incomplete coverage.','pending','high','follow_up',owner_id,p_now);
    UPDATE wholesale_ingest.monitor_incidents SET task_id=incident.task_id WHERE source_id=e.source_id AND day=e.day;
    UPDATE wholesale_ingest.expected_runs SET alert_task_id=incident.task_id WHERE source_id=e.source_id AND day=e.day;
   ELSIF incident.task_id IS NOT NULL THEN
    UPDATE public.tasks SET description=e.source_key||' ('||e.day||'): '||reason||'. Review the current receipt; no seller outreach was sent.',status='pending'
    WHERE id=incident.task_id;
   END IF;
  ELSIF latest.id IS NOT NULL AND count_batches=latest.expected_batches AND latest.processing_status='completed' THEN
   UPDATE wholesale_ingest.monitor_incidents SET resolved_at=coalesce(resolved_at,p_now),last_seen_at=p_now WHERE source_id=e.source_id AND day=e.day;
   -- Keep the assigned task for operator acknowledgement; do not silently close it.
  END IF;
 END LOOP;

 SELECT jsonb_build_object('day',today,'owner_configured',owner_id IS NOT NULL,
 'sources',(SELECT coalesce(jsonb_agg(jsonb_build_object('source_key',s.source_key,'enabled',s.enabled,'due_at',x.due_at,'status',coalesce(i.status,'not_received'),'processing_status',i.processing_status,'run_id',i.id,'status_reason',i.status_reason,'expected_batches',i.expected_batches,'received_batches',(SELECT count(*) FROM wholesale_ingest.raw_payloads b WHERE b.run_id=i.id),'records_in',(SELECT coalesce(sum(b.records_in),0) FROM wholesale_ingest.raw_payloads b WHERE b.run_id=i.id)) ORDER BY s.source_key),'[]')
 FROM wholesale_ingest.sources s LEFT JOIN wholesale_ingest.expected_runs x ON x.source_id=s.id AND x.day=wholesale_ingest.collection_due_day(s.collection_cadence,s.cadence_effective_on,today)
 LEFT JOIN LATERAL (SELECT r.* FROM wholesale_ingest.ingest_runs r WHERE r.source_id=s.id AND wholesale_ingest.collection_due_day(s.collection_cadence,s.cadence_effective_on,r.scheduled_for)=wholesale_ingest.collection_due_day(s.collection_cadence,s.cadence_effective_on,today) ORDER BY r.received_at DESC,r.id DESC LIMIT 1) i ON true),
 'new_leads',(SELECT coalesce(sum(records_new),0) FROM wholesale_ingest.ingest_runs WHERE scheduled_for=today),
 'stacked_records',(SELECT coalesce(sum(records_stacked),0) FROM wholesale_ingest.ingest_runs WHERE scheduled_for=today),
 'open_incidents',(SELECT coalesce(jsonb_agg(to_jsonb(m) ORDER BY day,source_id),'[]') FROM wholesale_ingest.monitor_incidents m WHERE resolved_at IS NULL),
 'top_ten',(SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY t.score DESC,t.created_at DESC,t.lead_id),'[]') FROM (SELECT latest_score.* FROM (SELECT DISTINCT ON (l.lead_id) l.lead_id,l.score,l.reasons,l.flags,l.route,l.created_at FROM wholesale_ingest.lead_evaluations l ORDER BY l.lead_id,l.created_at DESC,l.id DESC) latest_score WHERE score IS NOT NULL ORDER BY score DESC,created_at DESC,lead_id LIMIT 10) t)) INTO summary;
 -- Rank only stored evaluations; no model invocation or outreach from monitoring.
 INSERT INTO wholesale_ingest.daily_digests(day,generated_at,status,summary) VALUES(today,p_now,'generated',summary)
 ON CONFLICT(day) DO UPDATE SET generated_at=p_now,summary=excluded.summary;

 -- Retention is an explicit maintenance action. Monitoring never deletes intake evidence or contacts.
 RETURN summary;
END; $$;
COMMIT;
