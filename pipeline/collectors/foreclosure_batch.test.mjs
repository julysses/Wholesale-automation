import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { queryUrl, validateRows, fetchOwners, loadOwners, assessNotice, trusteeReferences } from './foreclosure_batch.mjs';

const row = { propid: '123', ownerid: '456', geoid: 'R-123', ownername: 'SYNTHETIC OWNER',
  situsconcat: '1 EXAMPLE LN , ANNA, TX 75409', datadate: '2026-10-14T00:48:00.000' };
const detail = { document_id: '42', source_url: 'https://apps2.collincountytx.gov/ForeclosureNotices/DetailPage/42',
  cad_property_id: '123', indexed_property_address: '1 Example Ln Anna, TX 75409', auction_date: '2026-12-01' };
const capture = { html_sha256: 'a'.repeat(64), expected_pages: 1 };
const page = { page: 1, text: 'TS. # 2026-12345-TX.\nCommonly known as: 1 EXAMPLE LN ANNA, TX 75409', review_required: false, text_sha256: 'b'.repeat(64) };

test('public ownership queries bind parcels, reject truncation/injection, and hash resume evidence', async () => {
  assert.throws(() => queryUrl(['123) OR true']), /Invalid/);
  assert.throws(() => queryUrl(['123', '123']), /Invalid/);
  assert.throws(() => validateRows([{ ...row, propid: '999' }], ['123']), /mismatch/);
  assert.throws(() => validateRows([row, row], ['123']), /Duplicate/);
  assert.throws(() => validateRows(Array(2001).fill(row), ['123']), /truncated/);
  const root = await mkdtemp(join(tmpdir(), 'owner-batch-'));
  try {
    let calls = 0;
    const stub = async url => { calls++; assert.equal(url, queryUrl(['123'])); return new Response(JSON.stringify([row]), { headers: { 'Content-Type': 'application/json' } }); };
    const snapshot = await fetchOwners(['123', '123'], root, stub);
    assert.equal(calls, 1); assert.deepEqual((await loadOwners(join(root, 'snapshot.json'))).rows, snapshot.rows);
    await writeFile(join(root, 'batch-0.json'), JSON.stringify([{ ...row, situsconcat: '9 WRONG ST' }]));
    await assert.rejects(loadOwners(join(root, 'snapshot.json')), /changed/);
    await assert.rejects(fetchOwners(['123'], root, async () => new Response('<html>login</html>', { headers: { 'Content-Type': 'text/html' } })), /failed/);
  } finally { await rm(root, { recursive: true, force: true }); }
});

test('bulk triage preserves holds for stale data, mismatched units, co-owners, past sales and uncertain OCR', () => {
  const result = assessNotice(detail, capture, [page], [row], '2026-10-14');
  assert.equal(result.appraisal_situs_matched, true); assert.equal(result.trustee_case, '2026-12345-TX');
  assert.equal(result.trace_eligible, false); assert.equal(result.identity_verified, false); assert.deepEqual(result.holds, []);
  assert.equal(assessNotice(detail, capture, [page], [{ ...row, datadate: '2026-10-10T00:00:00' }], '2026-10-14').appraisal_situs_matched, false);
  assert.ok(assessNotice(detail, capture, [page], [{ ...row, situsconcat: '1 EXAMPLE LN UNIT B, ANNA TX 75409' }], '2026-10-14').holds.includes('situs_mismatch'));
  assert.ok(assessNotice(detail, capture, [page], [row, { ...row, ownerid: '789' }], '2026-10-14').holds.includes('multiple_appraisal_owners'));
  assert.ok(assessNotice({ ...detail, auction_date: '2026-10-06' }, capture, [page], [row], '2026-10-14').holds.includes('sale_date_not_future'));
  assert.ok(assessNotice(detail, capture, [{ ...page, review_required: true }], [row], '2026-10-14').holds.includes('text_quality_review'));
  assert.equal(assessNotice(detail, capture, [{ ...page, text: 'Owner mailing address only' }], [row], '2026-10-14').notice_situs_supported, false);
  assert.throws(() => assessNotice(detail, capture, [page], [row], '2026-02-30'), /Invalid/);
});


test('labelled trustee references support intact formats without repairing damaged OCR or reading instrument numbers', () => {
  for (const [text, expected] of [
    ['PLG File Number: 26-012345-1 3', 'PLG:26-012345-1'],
    ['Firm File Number: 26-012345', 'FIRM:26-012345'],
    ['TS#: 26-12345', 'TS:26-12345'],
    ['TS No.: 26-12345', 'TS:26-12345'],
    ['T.S. # 2026-12345-TX', '2026-12345-TX'],
  ]) assert.deepEqual(trusteeReferences(text), [expected]);
  for (const text of ['PLG File Number: 260123451', 'Firm File Number: 26012345', 'TS#: 2612345',
    'Loan Number: 26-012345', 'County Clerk File Number: 26-012345', 'PLG File Number:\n26-012345-1',
    'PLG File Number: 26-012345-1-X', 'Firm File Number: 26-012345-1', 'TS#: 26-12345-7',
    'TS#: 26-12345X', 'TS#: 26-123456', 'RTS 2026-12345-TX']) {
    assert.deepEqual(trusteeReferences(text), [], text);
  }
});

test('repeated references retain page provenance; ambiguous references and OCR quality remain held', () => {
  const pages = [1,2].map(n=>({...page,page:n,text:page.text.replace('TS. # 2026-12345-TX.','PLG File Number: 26-012345-1')}));
  const result=assessNotice(detail,{...capture,expected_pages:2},pages,[row],'2026-10-14');
  assert.equal(result.trustee_case,'PLG:26-012345-1');
  assert.deepEqual(result.evidence.filter(e=>e.field==='trustee_case').map(e=>e.page),[1,2]);
  for(const flag of ['identity_verified','current_status_verified','trace_eligible','outreach_authorized'])assert.equal(result[flag],false);
  const ambiguous=assessNotice(detail,capture,[{...pages[0],text:pages[0].text+'\nPLG File Number: 26-012345-2'}],[row],'2026-10-14');
  assert.equal(ambiguous.trustee_case,null);assert.ok(ambiguous.holds.includes('trustee_case_unresolved'));
  const quality=assessNotice(detail,capture,[{...pages[0],review_required:true}],[row],'2026-10-14');
  assert.ok(quality.holds.includes('text_quality_review'));assert.equal(quality.trace_eligible,false);
});
