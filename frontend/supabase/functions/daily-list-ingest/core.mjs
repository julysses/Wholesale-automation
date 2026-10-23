// Pure helpers shared by collector signing, Edge ingress and local tests.
export function canonicalJSON(v) {
  if (Array.isArray(v)) return '[' + v.map(canonicalJSON).join(',') + ']';
  if (v !== null && typeof v === 'object') return '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canonicalJSON(v[k])).join(',') + '}';
  return JSON.stringify(v);
}
export async function sha256(text) {
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(hash), b => b.toString(16).padStart(2, '0')).join('');
}
export function equalHash(a, b) {
  if (!/^[a-f0-9]{64}$/.test(a) || !/^[a-f0-9]{64}$/.test(b)) return false;
  let diff = 0; for (let i=0;i<64;i++) diff |= a.charCodeAt(i)^b.charCodeAt(i); return diff===0;
}
export function semanticErrors(p, now = new Date()) {
  const e=[]; const err=(path,message)=>e.push({path,message});
  if ((p.batch_index??0)>=(p.batch_count??1)) err('/batch_index','must be less than batch_count');
  if (p.window_start > p.window_end) err('/window_start','must not exceed window_end');
  const days=(Date.parse(p.window_end)-Date.parse(p.window_start))/86400000+1;
  if (days>p.lookback_days) err('/lookback_days','must cover the inclusive window');
  if (p.source.list_type==='pre_foreclosure' && (p.lookback_days>30 || days>30)) err('/lookback_days','pre-foreclosure maximum is 30 days, including backfills');
  if (Date.parse(p.pulled_at)>now.getTime()+300000) err('/pulled_at','cannot be in the future');
  if (p.status==='success'&&!p.coverage_complete) err('/coverage_complete','success requires verified complete coverage');
  if (p.status!=='success'&&!p.status_reason.trim()) err('/status_reason','required for partial, blocked and failed');
  if (['blocked','failed'].includes(p.status)&&p.records.length) err('/records','use partial when usable records were collected');
  const keys=new Set();
  p.records.forEach((r,i)=>{
    if (r.source_record_id) { if(keys.has(r.source_record_id)) err(`/records/${i}/source_record_id`,'duplicate ID within payload'); keys.add(r.source_record_id); }
    if(r.filed_date&&(r.filed_date<p.window_start||r.filed_date>p.window_end)&&p.source.list_type!=='tax_delinquent') err(`/records/${i}/filed_date`,'outside declared filing window');
    if(r.state&&r.state!==p.source.state) err(`/records/${i}/state`,'must match source state');
    if(r.amount_owed!==null&&r.amount_type==='unknown') err(`/records/${i}/amount_type`,'known amount requires its meaning');
  });
  return e;
}
const norm=v=>(v??'').normalize('NFKC').trim().toLowerCase().replace(/\s+/g,' ');
export function propertyAliases(source,r) {
  const prefix=`${norm(source.state)}|${norm(source.county)}|`;
  const aliases=[];
  // Preserve parcel punctuation/leading zeros: county-specific normalization needs reviewed rules.
  if(r.parcel_id?.trim()) aliases.push(prefix+'parcel|'+norm(r.parcel_id));
  if(r.property_address?.trim()&&r.city?.trim()&&r.zip?.trim()) aliases.push(prefix+'address|'+[r.property_address,r.unit,r.city,r.zip].map(norm).join('|'));
  return aliases;
}
export function resolutionGate(p,r) {
  if(!r.source_record_id) return 'missing_source_id';
  if(!propertyAliases(p.source,r).length) return 'missing_property_identity';
  if(p.source.list_type==='pre_foreclosure'&&!r.filed_date) return 'missing_filing_date';
  // Probate never auto-links an estate merely because a party address appears.
  if(p.source.list_type==='probate') return 'verify_estate_property_link';
  // County/property evidence is approved by an operator, never trusted from collector raw data.
  return 'verify_county_property_evidence';
}
