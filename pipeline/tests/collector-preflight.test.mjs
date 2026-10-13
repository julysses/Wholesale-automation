import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {preflight} from '../collectors/preflight.mjs';
import {canonicalJSON, sha256} from '../../frontend/supabase/functions/daily-list-ingest/core.mjs';
const fixture = () => JSON.parse(fs.readFileSync(new URL('../fixtures/synthetic.json', import.meta.url)));
const coverage = () => JSON.parse(fs.readFileSync(new URL('../fixtures/synthetic-coverage.json', import.meta.url)));
const now = new Date('2026-10-13T15:00:00Z');
test('preflight validates synthetic evidence but never claims delivery', async () => {
  const result = await preflight(fixture(), now, coverage());
  assert.equal(result.valid, true); assert.equal(result.delivered, false);
});
test('unknown or mismatched source cannot pass a reviewed procedure', async () => {
  for (const change of [p => p.source_key = 'tx-dallas-probate', p => p.source.county = 'Collin']) {
    const p = fixture(); change(p); assert.equal((await preflight(p, now, p.coverage_complete ? coverage() : undefined)).valid, false);
  }
});
test('modified records and unreviewed hosts fail even with a fresh valid hash', async () => {
  const p = fixture(); p.records[0].owner_name = 'Changed';
  assert.equal((await preflight(p, now, p.coverage_complete ? coverage() : undefined)).valid, false);
  for (const url of ['https://www.dallascounty.org.evil.example/notice', 'https://user:pass@www.dallascounty.org/notice', 'http://www.dallascounty.org/notice']) {
    p.records[0].source_url = url; p.records_sha256 = await sha256(canonicalJSON(p.records));
    assert.equal((await preflight(p, now, p.coverage_complete ? coverage() : undefined)).valid, false);
  }
});
test('officially linked Dallas public search host is recognized locally', async () => {
  const p = fixture(); p.source.source_url = 'https://dallas.tx.publicsearch.us/';
  assert.equal((await preflight(p, now, p.coverage_complete ? coverage() : undefined)).valid, true);
});
test('incomplete empty coverage cannot masquerade as success', async () => {
  const p = fixture(); p.records = []; p.records_sha256 = await sha256('[]'); p.coverage_complete = false;
  assert.equal((await preflight(p, now, p.coverage_complete ? coverage() : undefined)).valid, false);
  p.status = 'blocked'; p.status_reason = 'Login required';
  assert.equal((await preflight(p, now, p.coverage_complete ? coverage() : undefined)).valid, true);
});
test('oversized evidence is rejected without truncation', async () => {
  const p = fixture(); p.records[0].raw = {text: 'x'.repeat(2 * 1024 * 1024)};
  p.records_sha256 = await sha256(canonicalJSON(p.records));
  assert.equal((await preflight(p, now, p.coverage_complete ? coverage() : undefined)).valid, false);
});
