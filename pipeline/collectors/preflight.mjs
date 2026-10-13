// Offline validation only. Never submits records or enables a source.
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
import Ajv from 'ajv';
import addFormats from 'ajv-formats';
import {coverageErrors} from './coverage.mjs';
import {canonicalJSON, sha256, semanticErrors} from '../../frontend/supabase/functions/daily-list-ingest/core.mjs';

const ajv = new Ajv({allErrors: true, strict: true});
addFormats(ajv);
const validate = ajv.compile(JSON.parse(fs.readFileSync(new URL('../../frontend/supabase/functions/daily-list-ingest/ingest.schema.json', import.meta.url))));
const sources = {
  'tx-dallas-pre_foreclosure': {county: 'Dallas', jurisdiction: 'Dallas County', hosts: ['www.dallascounty.org', 'dallas.tx.publicsearch.us']},
  'tx-collin-pre_foreclosure': {county: 'Collin', jurisdiction: 'Collin County', hosts: ['apps2.collincountytx.gov', 'www.collincountytx.gov']},
};
const allowedURL = (value, hosts) => {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password && !url.port && hosts.includes(url.hostname);
  } catch { return false; }
};

export async function preflight(payload, now = new Date(), coverage) {
  if (!validate(payload)) return {valid: false, delivered: false, errors: validate.errors.map(e => ({path: e.instancePath, message: e.message}))};
  const errors = semanticErrors(payload, now);
  const source = sources[payload.source_key];
  const error = (path, message) => errors.push({path, message});
  if (!source) error('/source_key', 'No reviewed collection procedure for this source');
  else {
    if (payload.source.state !== 'TX' || payload.source.county !== source.county || payload.source.jurisdiction !== source.jurisdiction || payload.source.list_type !== 'pre_foreclosure') error('/source', 'Source identity does not match reviewed procedure');
    if (!allowedURL(payload.source.source_url, source.hosts)) error('/source/source_url', 'Expected an exact reviewed HTTPS host');
    payload.records.forEach((record, index) => {
      if (!allowedURL(record.source_url, source.hosts)) error(`/records/${index}/source_url`, 'Expected an exact reviewed HTTPS host');
    });
  }
  if (await sha256(canonicalJSON(payload.records)) !== payload.records_sha256) error('/records_sha256', 'Records differ from the recorded hash');
  if (payload.coverage_complete) {
    if (!coverage) error('/coverage', 'Complete coverage requires a reviewed coverage ledger');
    else errors.push(...coverageErrors(payload, coverage, url => !!source && allowedURL(url, source.hosts), now));
  } else if (coverage !== undefined) error('/coverage', 'Use the coverage ledger only for complete runs; retain incomplete evidence separately');
  if (Buffer.byteLength(JSON.stringify(payload), 'utf8') > 2 * 1024 * 1024) error('/', 'Payload exceeds 2 MiB; prepare bounded batches without truncation');
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
