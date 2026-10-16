/** Bulk public ownership corroboration and OCR triage. Never grants tracing eligibility. */
import { readFile, writeFile, mkdir, rename } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { fileURLToPath } from 'node:url';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { validateInputs, engine } from './notice_ocr.mjs';

export const datasetUrl = 'https://data.texas.gov/d/ahis-pci3';
export const endpoint = 'https://data.texas.gov/resource/ahis-pci3.json';
export const hash = value => createHash('sha256').update(value).digest('hex');
const normalize = value => String(value ?? '').toUpperCase().replace(/[^A-Z0-9]+/g, ' ').trim();
const validId = value => typeof value === 'string' && /^[1-9]\d{0,19}$/.test(value);
const validDay = value => /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value))
  && new Date(value).toISOString().slice(0, 10) === value;

export function queryUrl(ids) {
  if (!Array.isArray(ids) || !ids.length || ids.length > 100 || ids.some(id => !validId(id))
    || new Set(ids).size !== ids.length) throw Error('Invalid parcel query');
  const url = new URL(endpoint);
  url.searchParams.set('$where', `propid in(${[...ids].sort((a, b) => Number(a) - Number(b)).join(',')})`);
  // Up to 20 co-owner rows per property; reaching the bound aborts rather than hiding truncation.
  url.searchParams.set('$limit', '2001');
  url.searchParams.set('$order', 'propid,ownerid');
  return url.href;
}

export function validateRows(rows, ids) {
  if (!Array.isArray(rows) || rows.length >= 2001) throw Error('Invalid or potentially truncated ownership response');
  const expected = new Set(ids), seen = new Set();
  for (const row of rows) {
    if (!row || !expected.has(row.propid) || !validId(row.ownerid)
      || typeof row.ownername !== 'string' || !row.ownername.trim()
      || typeof row.situsconcat !== 'string' || typeof row.geoid !== 'string'
      || typeof row.datadate !== 'string' || !validDay(row.datadate.slice(0, 10))) throw Error('Ownership schema or parcel mismatch');
    const key = `${row.propid}:${row.ownerid}`;
    if (seen.has(key)) throw Error('Duplicate ownership row');
    seen.add(key);
  }
  return rows;
}

async function privateJson(path, value) {
  await writeFile(path + '.tmp', JSON.stringify(value, null, 2), { mode: 0o600 });
  await rename(path + '.tmp', path);
}

export async function fetchOwners(ids, output, fetchImpl = fetch) {
  if (!Array.isArray(ids) || !ids.length || ids.some(id => !validId(id))) throw Error('Invalid parcel inventory');
  ids = [...new Set(ids)].sort((a, b) => Number(a) - Number(b));
  if (ids.length > 500) throw Error('Oversized parcel inventory');
  await mkdir(output, { recursive: true, mode: 0o700 });
  const rows = [], batches = [];
  for (let offset = 0; offset < ids.length; offset += 100) {
    const batch = ids.slice(offset, offset + 100), url = queryUrl(batch);
    const response = await fetchImpl(url, { redirect: 'error', signal: AbortSignal.timeout(30000),
      headers: { Accept: 'application/json' } });
    if (!response.ok || !response.headers.get('content-type')?.includes('application/json')) throw Error('Public ownership download failed');
    // Bound the stream before parsing, including responses without a Content-Length.
    if (Number(response.headers.get('content-length') ?? 0) > 5_000_000) throw Error('Ownership response too large');
    const chunks = []; let size = 0;
    for await (const chunk of response.body) {
      size += chunk.length;
      if (size > 5_000_000) throw Error('Ownership response too large');
      chunks.push(chunk);
    }
    const bytes = Buffer.concat(chunks), found = validateRows(JSON.parse(bytes), batch);
    rows.push(...found);
    const file = `batch-${offset / 100}.json`;
    await writeFile(join(output, file), bytes, { mode: 0o600 });
    batches.push({ file, query_url: url, property_ids: batch, sha256: hash(bytes), row_count: found.length });
  }
  const snapshot = { schema_version: '1.0', dataset_url: datasetUrl, retrieved_at: new Date().toISOString(),
    property_ids: ids, rows, batches };
  await privateJson(join(output, 'snapshot.json'), snapshot);
  return snapshot;
}

export async function loadOwners(path) {
  const snapshot = JSON.parse(await readFile(path, 'utf8'));
  if (snapshot.schema_version !== '1.0' || snapshot.dataset_url !== datasetUrl
    || !Number.isFinite(Date.parse(snapshot.retrieved_at)) || !Array.isArray(snapshot.batches)
    || !Array.isArray(snapshot.property_ids) || snapshot.property_ids.some(id => !validId(id))
    || new Set(snapshot.property_ids).size !== snapshot.property_ids.length) throw Error('Invalid ownership snapshot');
  const rows = [], ids = [];
  for (const [index, batch] of snapshot.batches.entries()) {
    if (batch.file !== `batch-${index}.json` || batch.query_url !== queryUrl(batch.property_ids)) throw Error('Invalid ownership receipt');
    const bytes = await readFile(join(resolve(path, '..'), batch.file));
    if (hash(bytes) !== batch.sha256) throw Error('Ownership evidence changed');
    const found = validateRows(JSON.parse(bytes), batch.property_ids);
    if (found.length !== batch.row_count) throw Error('Ownership count mismatch');
    rows.push(...found); ids.push(...batch.property_ids);
  }
  if (new Set(ids).size !== ids.length || JSON.stringify(rows) !== JSON.stringify(snapshot.rows) || JSON.stringify(ids) !== JSON.stringify(snapshot.property_ids)) throw Error('Ownership snapshot mismatch');
  return snapshot;
}

// Extract only explicitly labelled, intact references. Never repair OCR-damaged digits
// or confuse recorded instruments, loan numbers and page numbers with trustee cases.
export function trusteeReferences(text) {
  const formats = [
    { prefix: '', pattern: /\b(?:T\.?[ \t]*S\.?[ \t]*(?:NO\.?[ \t]*)?[.#:]*[ \t]*)(\d{4}-\d{3,10}-[A-Z]{2})(?![\w-])/gi },
    { prefix: 'PLG:', pattern: /\bPLG[ \t]+File[ \t]+Number[ \t]*:[ \t]*(\d{2}-\d{6}-\d{1,3})(?![\w-])/gi },
    { prefix: 'FIRM:', pattern: /\bFirm[ \t]+File[ \t]+Number[ \t]*:[ \t]*(\d{2}-\d{6})(?![\w-])/gi },
    { prefix: 'TS:', pattern: /\bT\.?[ \t]*S\.?[ \t]*(?:NO\.?[ \t]*)?[.#:]+[ \t]*(\d{2}-\d{5})(?![\w-])/gi },
  ];
  const references = new Set();
  for (const {prefix, pattern} of formats) {
    for (const match of text.matchAll(pattern)) references.add(prefix + match[1].toUpperCase());
  }
  return [...references];
}

export function assessNotice(detail, capture, pages, ownerRows, day) {
  if (!validDay(day)) throw Error('Invalid processing day');
  const holds = [], evidence = [];
  if (!detail.cad_property_id) holds.push('parcel_missing');
  if (!ownerRows.length) holds.push('appraisal_record_missing');
  if (ownerRows.length > 1) holds.push('multiple_appraisal_owners');
  const fresh = ownerRows.length > 0 && ownerRows.every(row => validDay(row.datadate?.slice(0, 10) ?? '')
    && row.datadate.slice(0, 10) <= day && Date.parse(day) - Date.parse(row.datadate.slice(0, 10)) <= 86400000);
  if (ownerRows.length && !fresh) holds.push('appraisal_data_stale');
  const address = normalize(detail.indexed_property_address);
  const addressMatch = !!address && ownerRows.length > 0 && ownerRows.every(row => normalize(row.situsconcat) === address);
  if (ownerRows.length && !addressMatch) holds.push('situs_mismatch');
  const futureSale = validDay(detail.auction_date ?? '') && detail.auction_date > day;
  if (!futureSale) holds.push('sale_date_not_future');
  if (pages.some(page => page.review_required)) holds.push('text_quality_review');
  let addressOnNotice = false;
  const cases = new Set();
  for (const page of pages) {
    if (address && normalize(page.text).includes(address)) { addressOnNotice = true; evidence.push({ field: 'situs', page: page.page, text_sha256: page.text_sha256 }); }
    for (const value of trusteeReferences(page.text)) {
      cases.add(value); evidence.push({ field: 'trustee_case', value, page: page.page, text_sha256: page.text_sha256 });
    }
  }
  if (!addressOnNotice) holds.push('notice_situs_not_corroborated');
  if (cases.size !== 1) holds.push('trustee_case_unresolved');
  // Whole-document content/legal/owner/current-status review remains distinct from this triage.
  return { document_id: detail.document_id, source_url: detail.source_url, html_sha256: capture.html_sha256,
    expected_pages: capture.expected_pages, extracted_pages: pages.length, text_sha256s: pages.map(page => page.text_sha256), parcel_id: detail.cad_property_id ?? null,
    appraisal_situs_matched: addressMatch && fresh, notice_situs_supported: addressOnNotice,
    trustee_case: cases.size === 1 ? [...cases][0] : null, auction_date: detail.auction_date ?? null,
    future_sale: futureSale, holds, evidence, identity_verified: false, current_status_verified: false,
    trace_eligible: false, outreach_authorized: false };
}

export async function runBatch({ root, manifestPath, detailsPath, ocrRoot, ownersPath, output, day }) {
  if (!validDay(day)) throw Error('Invalid processing day');
  const captures = JSON.parse(await readFile(manifestPath, 'utf8'));
  await validateInputs(root, captures);
  const details = JSON.parse(await readFile(detailsPath, 'utf8'));
  if (!Array.isArray(details) || details.length !== captures.length
    || new Set(details.map(d => d.document_id)).size !== details.length) throw Error('Detail inventory mismatch');
  await promisify(execFile)('python3', [fileURLToPath(new URL('./verify_detail_inventory.py', import.meta.url)), root, detailsPath], { timeout: 30000 });
  const snapshot = await loadOwners(ownersPath), assessed = [];
  if (snapshot.retrieved_at.slice(0, 10) > day) throw Error('Ownership snapshot is from the future');
  for (const capture of captures) {
    const detail = details.find(d => d.document_id === capture.document_id);
    if (!detail || detail.source_url !== capture.source_url || detail.html_sha256 !== capture.html_sha256
      || capture.source_url !== `https://apps2.collincountytx.gov/ForeclosureNotices/DetailPage/${capture.document_id}`
      || detail.notice_pages_expected !== capture.expected_pages) throw Error('Collin detail evidence mismatch');
    const pages = [];
    for (const image of capture.pages) {
      const page = JSON.parse(await readFile(join(ocrRoot, capture.document_id, `page-${image.page}.json`), 'utf8'));
      if (page.engine !== engine || page.source_url !== capture.source_url || page.document_id !== capture.document_id
        || page.page !== image.page || page.image_sha256 !== image.sha256 || typeof page.text !== 'string'
        || page.text_sha256 !== hash(page.text) || !Number.isFinite(page.confidence) || page.confidence < 0 || page.confidence > 100
        || page.review_required !== (!page.text.trim() || page.confidence < 85) || page.verified !== false || page.trace_eligible !== false) throw Error('OCR evidence mismatch');
      pages.push(page);
    }
    assessed.push(assessNotice(detail, capture, pages, snapshot.rows.filter(row => row.propid === detail.cad_property_id), day));
  }
  const groups = new Map();
  for (const notice of assessed) {
    // Unmatched parcels cannot collapse unrelated notices into a property.
    const key = notice.appraisal_situs_matched ? `Collin:${notice.parcel_id}` : `notice:${notice.document_id}`;
    if (!groups.has(key)) groups.set(key, { key, document_ids: [], cases: {}, unresolved_case_documents: [] });
    const group = groups.get(key); group.document_ids.push(notice.document_id);
    // Same parcel is a property group; only same extracted case AND sale date is a repeat-case group.
    if (notice.trustee_case) {
      const caseKey = `${notice.trustee_case}:${notice.auction_date}`;
      (group.cases[caseKey] ??= []).push(notice.document_id);
    } else group.unresolved_case_documents.push(notice.document_id);
  }
  const propertyGroups = [...groups.values()];
  const summary = { county: 'Collin', documents: assessed.length, appraisal_situs_matched: assessed.filter(n => n.appraisal_situs_matched).length,
    notice_situs_supported: assessed.filter(n => n.notice_situs_supported).length, property_groups: propertyGroups.length,
    repeated_case_observations: propertyGroups.reduce((n, g) => n + Object.values(g.cases).reduce((count, ids) => count + ids.length - 1, 0), 0),
    future_sale_documents: assessed.filter(n => n.future_sale).length, exception_documents: assessed.filter(n => n.holds.length).length,
    evidence_review_candidates: assessed.filter(n => !n.holds.length).length, trace_eligible: 0 };
  const report = { schema_version: '1.0', processor: 'foreclosure-batch/1.1', day, processed_at: new Date().toISOString(),
    dataset_url: datasetUrl, ownership_snapshot_sha256: hash(await readFile(ownersPath)), summary, notices: assessed, groups: propertyGroups,
    verification_granted: false, dispatch_authorized: false, outreach_authorized: false };
  await mkdir(output, { recursive: true, mode: 0o700 });
  await privateJson(join(output, 'report.json'), report);
  await privateJson(join(output, 'receipt.json'), batchReceipt(report));
  return report;
}

export function batchReceipt(report) {
  const { processor, day, processed_at, dataset_url, ownership_snapshot_sha256 } = report;
  return { processor, day, processed_at, dataset_url, ownership_snapshot_sha256,
    report_sha256: hash(JSON.stringify(report)), verification_granted: false, dispatch_authorized: false, outreach_authorized: false,
    notices: report.notices.map(({ document_id, html_sha256, text_sha256s, parcel_id, appraisal_situs_matched,
      notice_situs_supported, trustee_case, auction_date, future_sale, holds }) => ({ document_id, html_sha256, text_sha256s,
      parcel_id, appraisal_situs_matched, notice_situs_supported, trustee_case, auction_date, future_sale, holds })) };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [, , action, ...args] = process.argv;
  if (action === 'owners' && args.length === 2) {
    const details = JSON.parse(await readFile(args[0], 'utf8'));
    const snapshot = await fetchOwners(details.filter(d => d.cad_property_id).map(d => d.cad_property_id), args[1]);
    console.log(JSON.stringify({ requested_properties: snapshot.property_ids.length, returned_rows: snapshot.rows.length, requests: snapshot.batches.length }));
  } else if (action === 'assess' && args.length === 7) {
    const [root, manifestPath, detailsPath, ocrRoot, ownersPath, output, day] = args;
    console.log(JSON.stringify((await runBatch({ root, manifestPath, detailsPath, ocrRoot, ownersPath, output, day })).summary));
  } else throw Error('Usage: foreclosure_batch.mjs owners details.json output | assess captures-root capture-manifest.json details.json ocr-root owners/snapshot.json output YYYY-MM-DD');
}
