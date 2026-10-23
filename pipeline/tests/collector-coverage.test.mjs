import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {spawnSync} from 'node:child_process';
import {preflight} from '../collectors/preflight.mjs';
import {canonicalJSON, sha256} from '../../frontend/supabase/functions/daily-list-ingest/core.mjs';
const fixture = name => JSON.parse(fs.readFileSync(new URL(`../fixtures/${name}.json`, import.meta.url)));
const now = new Date('2026-10-13T15:00:00Z');
async function rejected(change, message) {
  const p = fixture('synthetic'), c = fixture('synthetic-coverage');
  await change(p, c);
  const result = await preflight(p, now, c);
  assert.equal(result.valid, false);
  assert.equal(result.delivered, false);
  assert.ok(result.errors.some(e => message.test(e.message)), JSON.stringify(result.errors));
}
test('complete runs require coverage; stable reviewed synthetic coverage passes offline only', async () => {
  const p = fixture('synthetic');
  assert.equal((await preflight(p, now)).valid, false);
  const result = await preflight(p, now, fixture('synthetic-coverage'));
  assert.equal(result.valid, true); assert.equal(result.delivered, false);
});
test('changing county totals and missing pages cannot pass as complete', async () => {
  await rejected((p,c) => { c.page_size=1; c.scans[0].pages.push({page:2,total:2,documents:[]}); }, /total changed/);
  await rejected((p,c) => { c.scans[0].pages[0].total=51; }, /Missing or extra/);
});
test('duplicate document IDs, missing IDs and wrong filing windows fail', async () => {
  await rejected((p,c) => { const page=c.scans[0].pages[0]; page.total=2; page.documents.push({...page.documents[0]}); }, /Repeated document/);
  await rejected((p,c) => { c.scans[0].pages[0].documents[0].document_id=' '; }, /pattern/);
  await rejected((p,c) => { c.scans[0].pages[0].documents[0].filed_date='2026-08-20'; }, /outside/);
});
test('equal totals with changed IDs or filing dates still fail the verification scan', async () => {
  await rejected((p,c) => { c.scans[1].pages[0].documents[0].document_id='REPLACED'; }, /Verification scan changed/);
  await rejected((p,c) => { c.scans[1].pages[0].documents[0].filed_date='2026-10-10'; }, /Verification scan changed/);
});
test('ledger cannot be replayed against another run, window or record hash', async () => {
  for (const key of ['run_id','window_end','records_sha256']) {
    await rejected((p,c) => { p[key] = key==='run_id' ? '00000000-0000-4000-8000-000000000002' : key==='window_end' ? '2026-10-11' : '0'.repeat(64); }, /bind to this exact manifest/);
  }
});
test('unresolved and unreviewed documents prevent complete coverage', async () => {
  await rejected((p,c) => { c.reviews=[]; }, /Every indexed document/);
  await rejected((p,c) => { c.reviews[0].disposition='unresolved'; }, /Unresolved document/);
  for (const key of ['filing_stamp_verified','property_identity_verified','current_status_checked']) {
    await rejected((p,c) => { c.reviews[0][key]=false; }, /review is required|property\/current-status review/);
  }
});
test('review record identity, URLs and dates must reconcile to the actual payload', async () => {
  await rejected((p,c) => { c.reviews[0].record_ids=['MISSING']; }, /Included record must exist/);
  await rejected((p,c) => { c.reviews[0].document_url='https://evil.example/notice'; }, /reviewed HTTPS host/);
  await rejected((p,c) => { c.reviews[0].document_url='https://www.dallascounty.org/different'; }, /must match document review/);
  await rejected(async (p,c) => { p.records[0].filed_date='2026-10-10'; p.records_sha256=c.records_sha256=await sha256(canonicalJSON(p.records)); }, /must match document review/);
});
test('out-of-order scans, future reviews and multi-batch completeness fail closed', async () => {
  await rejected((p,c) => { c.scans[1].started_at='2026-10-12T04:00:00-05:00'; }, /follow the first/);
  await rejected((p,c) => { c.reviews[0].reviewed_at='2026-10-14T05:00:00-05:00'; }, /within this collection run/);
  await rejected((p,c) => { p.batch_count=2; }, /unbatched manifest/);
});
test('explicit reviewed exclusions allow zero included properties without losing indexed documents', async () => {
  const p=fixture('synthetic'), c=fixture('synthetic-coverage');
  p.records=[]; p.records_sha256=c.records_sha256=await sha256('[]');
  c.reviews[0].disposition='excluded'; c.reviews[0].record_ids=[];
  c.reviews[0].note='Synthetic withdrawn notice; reviewed exclusion, not a new lead.';
  assert.equal((await preflight(p,now,c)).valid,true);
});
test('a verified empty search requires two explicit zero-total pages', async () => {
  const p=fixture('synthetic'), c=fixture('synthetic-coverage');
  p.records=[]; p.records_sha256=c.records_sha256=await sha256('[]'); c.reviews=[];
  c.scans.forEach(s => { s.pages=[{page:1,total:0,documents:[]}]; });
  assert.equal((await preflight(p,now,c)).valid,true);
});
test('malformed coverage produces validation errors rather than an exception', async () => {
  for (const c of [null,{},[],{scans:null}]) assert.equal((await preflight(fixture('synthetic'),now,c)).valid,false);
});
test('CLI fails without coverage and succeeds with reviewed synthetic coverage', () => {
  const cli=new URL('../collectors/preflight.mjs',import.meta.url).pathname;
  const payload=new URL('../fixtures/synthetic.json',import.meta.url).pathname;
  const ledger=new URL('../fixtures/synthetic-coverage.json',import.meta.url).pathname;
  const missing=spawnSync(process.execPath,[cli,payload],{encoding:'utf8'});
  assert.equal(missing.status,1); assert.equal(JSON.parse(missing.stdout).delivered,false);
  const complete=spawnSync(process.execPath,[cli,payload,ledger],{encoding:'utf8'});
  assert.equal(complete.status,0,complete.stderr); assert.equal(JSON.parse(complete.stdout).valid,true);
});
