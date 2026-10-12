-- Rehearsal only. This transaction rolls back source enablement and all fixtures.
BEGIN;
DO $$
DECLARE src uuid; run uuid:=gen_random_uuid(); result jsonb; task uuid; scan_time timestamptz;
 target_day date:=(now() AT TIME ZONE 'America/Chicago')::date;
BEGIN
 scan_time:=(target_day+time '07:00') AT TIME ZONE 'America/Chicago';
 ASSERT NOT EXISTS(SELECT 1 FROM wholesale_ingest.sources WHERE enabled), 'Expected disabled rehearsal sources';
 UPDATE wholesale_ingest.sources SET enabled=true,procedure_approved_at=(target_day+time '00:00') AT TIME ZONE 'America/Chicago'
 WHERE source_key='tx-dallas-pre_foreclosure' RETURNING id INTO src;
 result:=wholesale_ingest.scan_at(scan_time);
 ASSERT (result->>'owner_configured')::boolean, 'Rehearsal owner must be configured';
 SELECT task_id INTO task FROM wholesale_ingest.monitor_incidents WHERE source_id=src AND monitor_incidents.day=target_day;
 ASSERT task IS NOT NULL, 'Missing-delivery task absent';
 result:=wholesale_ingest.scan_at(scan_time);
 ASSERT (SELECT task_id=task FROM wholesale_ingest.monitor_incidents WHERE source_id=src AND monitor_incidents.day=target_day), 'Duplicate alert task';
 INSERT INTO wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,status,status_reason,manifest_hash,expected_batches)
 VALUES(run,src,target_day,scan_time,'blocked','synthetic monitor rollback',repeat('a',64),1);
 INSERT INTO wholesale_ingest.raw_payloads(run_id,batch_index,payload_hash,records_hash,payload,records_in)
 VALUES(run,0,repeat('b',64),repeat('c',64),'{"private":"synthetic"}',0);
 result:=wholesale_ingest.scan_at(scan_time);
 ASSERT (SELECT kind='blocked' AND task_id=task FROM wholesale_ingest.monitor_incidents WHERE source_id=src AND monitor_incidents.day=target_day), 'Blocked run not surfaced';
 UPDATE wholesale_ingest.ingest_runs SET status='success',status_reason='' WHERE id=run;
 result:=wholesale_ingest.scan_at(scan_time);
 ASSERT (SELECT resolved_at IS NOT NULL FROM wholesale_ingest.monitor_incidents WHERE source_id=src AND monitor_incidents.day=target_day), 'Recovery not recorded';
 UPDATE wholesale_ingest.raw_payloads SET expires_at=scan_time-interval '1 second' WHERE run_id=run;
 result:=wholesale_ingest.scan_at(scan_time);
 ASSERT (SELECT payload IS NULL AND purged_at IS NOT NULL AND payload_hash=repeat('b',64) FROM wholesale_ingest.raw_payloads WHERE run_id=run), 'Retention lost receipt or retained raw content';
 ASSERT (SELECT delivered_at IS NULL FROM wholesale_ingest.daily_digests WHERE daily_digests.day=target_day), 'Generation must not claim delivery';
END $$;
ROLLBACK;
