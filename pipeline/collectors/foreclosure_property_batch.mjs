/** Build a whole-county property verification queue. Never authorizes paid tracing. */
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { runBatch, loadOwners, hash } from './foreclosure_batch.mjs';

const norm = value => String(value ?? '').toUpperCase().replace(/[^A-Z0-9]+/g, ' ').trim();
// County detail panels append city taxing-jurisdiction annotations. Preserve all other legal text.
const legal = value => norm(String(value ?? '').replace(/\(C[a-z]{2}\)/gi, ''));
const addressKey = row => [norm(row.property_address), norm(row.city), row.zip].join('|');
const csv = value => '"'+String(value??'').replaceAll('"','""')+'"';
export function contactQueueCsv(properties) {
  const headers = ['First Name','Last Name','Email','Phone','Mobile Phone','Landline','Street Address','City','State','Zip',
    'Mail Street Address','Mail City','Mail State','Mail Zip','Mail Address Same','Type','Status'];
  const rows = properties.map(p => [p.owner_name,'','','','','',p.identity.property_address,p.identity.city,'TX',p.identity.zip,
    '','','','','','Owner','New']);
  return [headers,...rows].map(row=>row.map(csv).join(',')).join('\r\n')+'\r\n';
}
export function buildProperties(details, snapshot, assessments, indexRows, existing, day) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || snapshot.dataset_url !== 'https://data.texas.gov/d/ahis-pci3') throw Error('Invalid source/day');
  const groups = new Map(), held = [], reused = [], index = new Map();
  for (const row of indexRows) {
    if (index.has(row.document_id) || !/^\d{1,30}$/.test(row.document_id) || !/^[a-f0-9]{32}$/.test(row.source_fingerprint)) throw Error('Invalid saved county index');
    index.set(row.document_id, row);
  }
  for (const detail of details) {
    const saved = index.get(detail.document_id), assessment = assessments.find(n => n.document_id === detail.document_id);
    if (!saved || !assessment || assessment.html_sha256 !== detail.html_sha256) throw Error('Unbound county evidence');
    const owners = snapshot.rows.filter(o => o.propid === detail.cad_property_id);
    const reasons = [];
    if (!assessment.future_sale) reasons.push('sale_date_not_future');
    if (!assessment.appraisal_situs_matched) reasons.push('fresh_situs_match_required');
    if (owners.length !== 1) reasons.push('single_appraisal_owner_row_required');
    const owner = owners[0];
    if (!detail.indexed_legal_description || !owner?.legaldescription || legal(detail.indexed_legal_description) !== legal(owner.legaldescription)) reasons.push('legal_description_mismatch');
    const situs = owner?.situsconcat?.match(/^(.+?)\s*,\s*(.+?)\s*,\s*TX\s+(\d{5})(?:-\d{4})?$/i);
    if (!situs || !owner?.geoid?.trim() || !owner.ownername?.trim()) reasons.push('appraisal_identity_incomplete');
    if (reasons.length) { held.push({ document_id: detail.document_id, reasons }); continue; }
    const identity = { property_address: situs[1].trim(), city: situs[2].trim(), state: 'TX', zip: situs[3], parcel_id: owner.geoid, unit: null };
    // Reuse known properties without editing owner inputs of an outstanding paid request.
    if (existing.some(p => p.county === 'Collin' && (p.parcel_id === identity.parcel_id || addressKey(p) === addressKey(identity)))) {
      reused.push({ document_id: detail.document_id, parcel_id: identity.parcel_id }); continue;
    }
    if (saved.resolved) { held.push({ document_id: detail.document_id, reasons: ['resolved_record_requires_recovery'] }); continue; }
    const key = identity.parcel_id;
    if (!groups.has(key)) groups.set(key, { identity, cad_property_id: owner.propid, owner_name: [owner.ownername,owner.ownernameaddtl].filter(Boolean).join(' '),
      evidence_url: `https://esearch.collincad.org/Property/View/${owner.propid}?year=${day.slice(0,4)}&ownerId=${owner.ownerid}&isUDI=false`,
      notices: [], active_signal: false, trace_eligible: false, outreach_authorized: false,
      stage: 'current_status_review', all_notice_pages_reviewed: false });
    const group = groups.get(key);
    if (addressKey(group.identity) !== addressKey(identity)) throw Error('Conflicting parcel situs');
    group.notices.push({ ...saved, source_url: detail.source_url, auction_date: detail.auction_date, html_sha256: detail.html_sha256 });
  }
  return { properties: [...groups.values()], held, reused, summary: { new_properties: groups.size,
    mapped_notice_observations: [...groups.values()].reduce((n,g)=>n+g.notices.length,0), held_notices: held.length,
    reused_notice_observations: reused.length, trace_eligible: 0, outreach_authorized: false } };
}

export async function buildQueue({ root, manifestPath, detailsPath, ocrRoot, ownersPath, indexPath, existingPath, output, day }) {
  const assessment = await runBatch({root,manifestPath,detailsPath,ocrRoot,ownersPath,output:join(output,'assessment'),day});
  const details = JSON.parse(await readFile(detailsPath,'utf8')), snapshot = await loadOwners(ownersPath);
  const result = buildProperties(details,snapshot,assessment.notices,JSON.parse(await readFile(indexPath,'utf8')),JSON.parse(await readFile(existingPath,'utf8')),day);
  const queue = { schema_version:'1.0',processor:'foreclosure-property-batch/1.0',processed_at:new Date().toISOString(),day,
    ownership_snapshot_sha256:hash(await readFile(ownersPath)),assessment_sha256:hash(JSON.stringify(assessment)),...result,
    verification_scope:'Current appraisal situs and legal matched to county detail metadata; full notice/current-sale/contacts remain held.',
    dispatch_authorized:false };
  await mkdir(output,{recursive:true,mode:0o700});
  await writeFile(join(output,'property-queue.json'),JSON.stringify(queue,null,2),{mode:0o600});
  // Address-only property matching: no guessed owner splits or invented mailing addresses.
  const addresses = [['Address','City','State','Zip'],...queue.properties.map(p=>[p.identity.property_address,p.identity.city,'TX',p.identity.zip])];
  await writeFile(join(output,'property-addresses.csv'),addresses.map(row=>row.map(csv).join(',')).join('\r\n')+'\r\n',{mode:0o600});
  // This stages a named verification queue only; it is not a paid submission manifest.
  await writeFile(join(output,'propstream-property-queue.csv'),contactQueueCsv(queue.properties),{mode:0o600});
  return queue;
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [root,manifestPath,detailsPath,ocrRoot,ownersPath,indexPath,existingPath,output,day]=process.argv.slice(2);
  if (!day || process.argv.length!==11) throw Error('Usage: foreclosure_property_batch.mjs captures-root captures.json details.json ocr-root owners/snapshot.json saved-index.json existing-properties.json output YYYY-MM-DD');
  console.log(JSON.stringify((await buildQueue({root,manifestPath,detailsPath,ocrRoot,ownersPath,indexPath,existingPath,output,day})).summary));
}
