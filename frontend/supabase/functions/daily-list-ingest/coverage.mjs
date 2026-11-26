// Shared Edge/collector evidence reconciliation; assertions are not reviewer authentication.
import {canonicalJSON} from './core.mjs';
const object = properties => ({type: 'object', additionalProperties: false, required: Object.keys(properties), properties});
const text = {type: 'string', minLength: 1, maxLength: 2000, pattern: '\\S'};
const date = {type: 'string', format: 'date'};
const timestamp = {type: 'string', format: 'date-time'};
const document = object({document_id: text, filed_date: date});
const page = object({
  page: {type: 'integer', minimum: 1},
  total: {type: 'integer', minimum: 0, maximum: 100000},
  documents: {type: 'array', maxItems: 2000, items: document},
});
const scan = object({
  started_at: timestamp, finished_at: timestamp,
  pages: {type: 'array', minItems: 1, maxItems: 2000, items: page},
});
export const coverageSchema = object({
  schema_version: {const: '1.0'}, source_key: text,
  run_id: {type: 'string', format: 'uuid'}, window_start: date, window_end: date,
  records_sha256: {type: 'string', pattern: '^[a-f0-9]{64}$'},
  page_size: {type: 'integer', minimum: 1, maximum: 2000},
  scans: {type: 'array', minItems: 2, maxItems: 2, items: scan},
  reviews: {type: 'array', maxItems: 100000, items: object({
    document_id: text, document_url: {type: 'string', format: 'uri'},
    disposition: {enum: ['included', 'excluded', 'unresolved']},
    record_ids: {type: 'array', uniqueItems: true, maxItems: 2000, items: text},
    reviewer: text, reviewed_at: timestamp, note: text,
    filing_stamp_verified: {type: 'boolean'},
    property_identity_verified: {type: 'boolean'}, current_status_checked: {type: 'boolean'},
  })},
});

export function coverageErrors(payload, ledger, allowedURL, now = new Date(), validate) {
  if (!validate(ledger)) return validate.errors.map(e => ({path: `/coverage${e.instancePath}`, message: e.message}));
  const errors = [];
  const err = (path, message) => errors.push({path: `/coverage${path}`, message});
  for (const key of ['source_key', 'run_id', 'window_start', 'window_end', 'records_sha256']) {
    if (ledger[key] !== payload[key]) err(`/${key}`, 'Ledger must bind to this exact manifest');
  }
  // Cross-batch coverage needs all manifests, not a claim from one fragment.
  if ((payload.batch_count ?? 1) !== 1 || (payload.batch_index ?? 0) !== 0) err('/', 'Complete coverage reconciliation currently requires one unbatched manifest');
  const scans = ledger.scans.map((scan, s) => {
    if (Date.parse(scan.started_at) > Date.parse(scan.finished_at) || Date.parse(scan.finished_at) > Date.parse(payload.pulled_at)) err(`/scans/${s}`, 'Scan must finish after its start and before manifest pull time');
    if (s && Date.parse(scan.started_at) < Date.parse(ledger.scans[s - 1].finished_at)) err(`/scans/${s}`, 'Verification scan must follow the first scan');
    const total = scan.pages[0].total;
    if (scan.pages.length !== Math.max(1, Math.ceil(total / ledger.page_size))) err(`/scans/${s}/pages`, 'Missing or extra result pages');
    const ids = new Set();
    const documents = [];
    scan.pages.forEach((p, i) => {
      if (p.page !== i + 1) err(`/scans/${s}/pages/${i}`, 'Pages must be contiguous and ordered from one');
      if (p.total !== total) err(`/scans/${s}/pages/${i}/total`, 'Result total changed during collection; restart the scan');
      const expected = Math.max(0, Math.min(ledger.page_size, total - i * ledger.page_size));
      if (p.documents.length !== expected) err(`/scans/${s}/pages/${i}/documents`, 'Page length does not match the advertised result range');
      p.documents.forEach(d => {
        if (ids.has(d.document_id)) err(`/scans/${s}`, 'Repeated document ID; do not deduplicate away a coverage gap');
        ids.add(d.document_id);
        if (d.filed_date < payload.window_start || d.filed_date > payload.window_end) err(`/scans/${s}`, 'Returned filing date is outside the requested window');
        documents.push(d);
      });
    });
    return documents;
  });
  if (canonicalJSON(ledger.scans[0].pages) !== canonicalJSON(ledger.scans[1].pages)) err('/scans', 'Verification scan changed; stable totals alone do not establish complete coverage');
  const documents = new Map(scans[0].map(d => [d.document_id, d]));
  const records = new Map(payload.records.map(r => [r.source_record_id, r]));
  const reviewed = new Set();
  const included = new Set();
  ledger.reviews.forEach((r, i) => {
    const path = `/reviews/${i}`;
    if (!documents.has(r.document_id) || reviewed.has(r.document_id)) err(path, 'Review must identify exactly one collected document');
    reviewed.add(r.document_id);
    if (!allowedURL(r.document_url)) err(path, 'Review document must use an exact reviewed HTTPS host');
    if (Date.parse(r.reviewed_at) < Date.parse(ledger.scans[0].started_at) || Date.parse(r.reviewed_at) > Date.parse(payload.pulled_at) || Date.parse(r.reviewed_at) > now.getTime() + 300000) err(path, 'Review timestamp must fall within this collection run');
    if (r.disposition === 'unresolved') err(path, 'Unresolved document prevents complete coverage');
    if (!r.filing_stamp_verified) err(path, 'Filing stamp review is required');
    if (r.disposition !== 'included' && r.record_ids.length) err(path, 'Only included documents may map to manifest records');
    if (r.disposition === 'included' && (!r.record_ids.length || !r.property_identity_verified || !r.current_status_checked)) err(path, 'Included documents need records and property/current-status review');
    r.record_ids.forEach(id => {
      const record = records.get(id);
      if (!record || included.has(id)) err(path, 'Included record must exist exactly once in the manifest and ledger');
      included.add(id);
      if (record && (record.filed_date !== documents.get(r.document_id)?.filed_date || record.source_url !== r.document_url)) err(path, 'Record filing date and evidence URL must match document review');
    });
  });
  if (reviewed.size !== documents.size) err('/reviews', 'Every indexed document needs an explicit reviewed disposition');
  if (included.size !== payload.records.length || payload.records.some(r => !included.has(r.source_record_id))) err('/reviews', 'Every manifest record needs a document review mapping');
  return errors;
}
