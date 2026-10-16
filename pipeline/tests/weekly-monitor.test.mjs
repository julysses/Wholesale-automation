import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {database} from './helpers.mjs';
test('weekly tax monitoring creates one expectation, accepts midweek receipt and renews Monday',async t=>{
 const db=await database();t.after(()=>db.close());
 await db.exec(fs.readFileSync(new URL('../../frontend/supabase/migrations/20261015023121_weekly_tax_monitoring.sql',import.meta.url),'utf8'));
 await db.exec(`UPDATE wholesale_ingest.sources SET enabled=true,procedure_approved_at='2026-10-14T12:00:00Z',cadence_effective_on='2026-10-14' WHERE source_key='tx-collin-tax_delinquent';
 SELECT wholesale_ingest.scan_at('2026-10-14T15:00:00Z');
 SELECT wholesale_ingest.scan_at('2026-10-15T15:00:00Z');
 SELECT wholesale_ingest.scan_at('2026-10-18T15:00:00Z');`);
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.expected_runs')).rows[0].n,1);
 await db.exec(`INSERT INTO wholesale_ingest.ingest_runs(id,source_id,scheduled_for,pulled_at,received_at,status,status_reason,manifest_hash,expected_batches)
 SELECT '00000000-0000-4000-8000-000000000001',id,'2026-10-15','2026-10-15T12:00:00Z','2026-10-15T12:00:00Z','success','',repeat('a',64),1 FROM wholesale_ingest.sources WHERE source_key='tx-collin-tax_delinquent';
 INSERT INTO wholesale_ingest.raw_payloads(run_id,batch_index,payload_hash,records_hash,payload,records_in,expires_at) VALUES('00000000-0000-4000-8000-000000000001',0,repeat('b',64),repeat('c',64),'{}',0,'2027-01-01');`);
 const summary=(await db.query("select wholesale_ingest.scan_at('2026-10-18T15:00:00Z') result")).rows[0].result;
 assert.equal(summary.open_incidents.length,0);
 assert.equal(summary.sources.find(s=>s.source_key==='tx-collin-tax_delinquent').status,'success');
 await db.exec("select wholesale_ingest.scan_at('2026-10-19T15:00:00Z')");
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.expected_runs')).rows[0].n,2);
 assert.equal((await db.query('select count(*)::int n from wholesale_ingest.monitor_incidents where resolved_at is null')).rows[0].n,1);
 await db.exec('set role authenticated');await assert.rejects(db.exec("select wholesale_ingest.collection_due_day('weekly','2026-10-14','2026-10-18')"),/permission denied/);
});
