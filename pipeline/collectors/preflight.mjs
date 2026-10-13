// Offline validation only. Never submits records or enables a source.
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import {coverageSchema} from '../../frontend/supabase/functions/daily-list-ingest/coverage.mjs';
import {collectorErrors} from '../../frontend/supabase/functions/daily-list-ingest/collector-policy.mjs';
import {canonicalJSON, sha256, semanticErrors} from '../../frontend/supabase/functions/daily-list-ingest/core.mjs';

const ajv = new Ajv({allErrors: true, strict: true});
addFormats(ajv);
const validateCoverage = ajv.compile(coverageSchema);
const validate = ajv.compile(JSON.parse(fs.readFileSync(new URL('../../frontend/supabase/functions/daily-list-ingest/ingest.schema.json', import.meta.url))));

export async function preflight(payload, now = new Date(), coverage) {
  if (!validate(payload)) return {valid: false, delivered: false, errors: validate.errors.map(e => ({path: e.instancePath, message: e.message}))};
  const errors = semanticErrors(payload, now);
  const error = (path, message) => errors.push({path, message});
  if (await sha256(canonicalJSON(payload.records)) !== payload.records_sha256) error('/records_sha256', 'Records differ from the recorded hash');
  if (coverage !== undefined && payload.coverage !== undefined && canonicalJSON(coverage) !== canonicalJSON(payload.coverage)) error('/coverage', 'Conflicting embedded and supplied coverage');
  const wire = coverage === undefined ? payload : {...payload, coverage};
  errors.push(...collectorErrors(wire, now, validateCoverage));
  if (Buffer.byteLength(JSON.stringify(wire), 'utf8') > 2 * 1024 * 1024) error('/', 'Payload exceeds 2 MiB; prepare bounded batches without truncation');
  return {valid: errors.length === 0, delivered: false, run_id: payload.run_id, source_key: payload.source_key, records: payload.records.length, errors};
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    if (![3, 4].includes(process.argv.length)) throw new Error('Usage: node pipeline/collectors/preflight.mjs manifest.json [coverage.json]');
    const file = process.argv[2];
    if (fs.statSync(file).size > 2 * 1024 * 1024) throw new Error('Payload exceeds 2 MiB');
    const coverageFile = process.argv[3];
    if (coverageFile && fs.statSync(coverageFile).size > 2 * 1024 * 1024) throw new Error('Coverage ledger exceeds 2 MiB');
    const coverage = coverageFile ? JSON.parse(fs.readFileSync(coverageFile, 'utf8')) : undefined;
    const result = await preflight(JSON.parse(fs.readFileSync(file, 'utf8')), new Date(), coverage);
    console.log(JSON.stringify(result, null, 2));
    process.exitCode = result.valid ? 0 : 1;
  } catch {
    console.error('Preflight failed: supply a readable JSON manifest and optional coverage ledger, each under 2 MiB. No data was submitted.');
    process.exitCode = 1;
  }
}
