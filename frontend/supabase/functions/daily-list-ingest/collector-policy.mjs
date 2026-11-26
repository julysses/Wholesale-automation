// Identical source/provenance and coverage rules at preflight and the authenticated Edge.
import {coverageErrors} from './coverage.mjs';
const sources = {
  'tx-dallas-pre_foreclosure': {county: 'Dallas', jurisdiction: 'Dallas County', hosts: ['www.dallascounty.org', 'dallas.tx.publicsearch.us']},
  'tx-dallas-tax_delinquent': {county: 'Dallas', jurisdiction: 'Dallas County', listType: 'tax_delinquent', hosts: ['www.dallascounty.org']},
  'tx-collin-tax_delinquent': {county: 'Collin', jurisdiction: 'Collin County', listType: 'tax_delinquent', hosts: ['www.collincountytx.gov']},
  'tx-collin-pre_foreclosure': {county: 'Collin', jurisdiction: 'Collin County', hosts: ['apps2.collincountytx.gov', 'www.collincountytx.gov']},
};
const allowedURL = (value, hosts) => {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password && !url.port && hosts.includes(url.hostname);
  } catch { return false; }
};

export function collectorErrors(payload, now, validateCoverage) {
  const errors = [];
  const coverage = payload.coverage;
  const source = sources[payload.source_key];
  const error = (path, message) => errors.push({path, message});
  if (!source) error('/source_key', 'No reviewed collection procedure for this source');
  else {
    if (payload.source.state !== 'TX' || payload.source.county !== source.county || payload.source.jurisdiction !== source.jurisdiction || payload.source.list_type !== (source.listType ?? 'pre_foreclosure')) error('/source', 'Source identity does not match reviewed procedure');
    if (!allowedURL(payload.source.source_url, source.hosts)) error('/source/source_url', 'Expected an exact reviewed HTTPS host');
    payload.records.forEach((record, index) => {
      if (!allowedURL(record.source_url, source.hosts)) error(`/records/${index}/source_url`, 'Expected an exact reviewed HTTPS host');
    });
  }
  if (source?.listType === 'tax_delinquent') {
    if (payload.coverage_complete) error('/coverage_complete', 'Tax snapshots require account and property review; complete coverage is not accepted by this procedure');
    if (!payload.source_as_of || payload.source_as_of !== payload.window_start || payload.source_as_of > payload.window_end || (Date.parse(payload.window_end)-Date.parse(payload.source_as_of))/86400000 > 10) error('/source_as_of', 'Tax snapshot date must begin a current window of at most ten days');
    payload.records.forEach((r,i) => {
      if (r.raw.snapshot_date !== payload.source_as_of || r.raw.snapshot_only !== true || r.raw.identity_verified !== false) error(`/records/${i}/raw`, 'Expected explicit snapshot-only review provenance');
      if (r.amount_owed !== null) error(`/records/${i}/amount_owed`, 'Weekly balances cannot be represented as verified current payoff amounts');
    });
  }
  if (payload.coverage_complete) {
    if (!coverage) error('/coverage', 'Complete coverage requires a reviewed coverage ledger');
    else errors.push(...coverageErrors(payload, coverage, url => !!source && allowedURL(url, source.hosts), now, validateCoverage));
  } else if (coverage !== undefined) error('/coverage', 'Use the coverage ledger only for complete runs; retain incomplete evidence separately');
  return errors;
}
