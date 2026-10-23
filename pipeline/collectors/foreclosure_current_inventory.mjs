/** Match a captured, visible auction inventory to the existing property queue in one pass.
 * A listing is corroboration only: no ownership, notice review or tracing clearance is granted.
 */
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { hash } from './foreclosure_batch.mjs';
const norm = value => String(value ?? '').toUpperCase().replace(/[^A-Z0-9]+/g,' ').trim();
const suffix = { STREET:'ST', ROAD:'RD', DRIVE:'DR', LANE:'LN', COURT:'CT', TRAIL:'TRL', CIRCLE:'CIR', BOULEVARD:'BLVD', AVENUE:'AVE', PLACE:'PL', CROSSING:'XING', PARKWAY:'PKWY' };
export function addressKey(address) {
  const match = String(address).match(/^(.+?),\s*(.+?),\s*TX\s+(\d{5})(?:-\d{4})?$/i);
  if (!match) return null;
  const street = norm(match[1]).split(' ');
  // Expand only the suffix position, retaining house numbers, directionals and units.
  const end = street.length - 1;
  street[end] = suffix[street[end]] ?? street[end];
  return [street.join(' '),norm(match[2]),'TX',match[3]].join('|');
}
export function matchInventory(queue, inventory, day) {
  const url = new URL(inventory.url);
  if (url.origin !== 'https://www.auction.com' || !/^\/residential\/tx\/collin-county(?:\/|$)/i.test(url.pathname)
      || !Array.isArray(inventory.rows) || inventory.rows.length > 1000
      || !/^\d{4}-\d{2}-\d{2}$/.test(day) || !Number.isFinite(Date.parse(day))
      || new Date(day).toISOString().slice(0,10) !== day
      || !Number.isFinite(Date.parse(inventory.captured_at)) || inventory.captured_at.slice(0,10) !== day) throw Error('Invalid or stale visible inventory');
  const seen = new Set();
  for (const row of inventory.rows) {
    if (!row.url.startsWith('https://www.auction.com/details/') || seen.has(row.url) || !addressKey(row.address) || typeof row.text !== 'string') throw Error('Invalid or duplicate listing');
    seen.add(row.url);
  }
  return queue.properties.map(property => {
    const key = addressKey(`${property.identity.property_address}, ${property.identity.city}, TX ${property.identity.zip}`);
    if (!key) throw Error('Invalid property identity');
    const matches = inventory.rows.filter(row => addressKey(row.address) === key);
    const candidate = matches.length === 1 ? matches[0] : null;
    const days = candidate?.text.match(/\bStarts in (\d{1,3}) days\b/);
    const date = days ? new Date(Date.parse(day) + Number(days[1])*86400000).toISOString().slice(0,10) : null;
    const foreclosure = !!candidate && /\bForeclosure Sale\b/.test(candidate.text) && !/\bBank Owned\b|\bPrivate Seller\b/.test(candidate.text);
    const dateMatched = !!date && property.notices.some(n => n.auction_date === date);
    const stage = matches.length > 1 ? 'ambiguous_listing' : !candidate ? 'current_listing_not_found'
      : !foreclosure ? 'non_foreclosure_listing' : !dateMatched ? 'sale_date_unresolved' : 'current_listing_matched';
    return { parcel_id:property.identity.parcel_id, identity:property.identity, document_ids:property.notices.map(n=>n.document_id),
      stage, listing_url:candidate?.url ?? null, advertised_sale_date:date, captured_at:inventory.captured_at,
      listing_evidence_sha256:candidate ? hash(JSON.stringify(candidate)) : null,
      trace_eligible:false, outreach_authorized:false,
      remaining_checks:['full_notice_owner_legal_and_case','trustee_source_binding','existing_contact_reuse','exact_provider_quote'] };
  });
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const [queuePath,inventoryPath,output,day]=process.argv.slice(2);
  if (process.argv.length !== 6) throw Error('Usage: foreclosure_current_inventory.mjs queue.json visible-inventory.json output.json YYYY-MM-DD');
  const queueBytes=await readFile(queuePath), inventoryBytes=await readFile(inventoryPath);
  const rows=matchInventory(JSON.parse(queueBytes),JSON.parse(inventoryBytes),day);
  const summary=rows.reduce((counts,row)=>(counts[row.stage]=(counts[row.stage]??0)+1,counts),{});
  await writeFile(output,JSON.stringify({processor:'foreclosure-current-inventory/1.0',day,
    queue_sha256:hash(queueBytes),inventory_sha256:hash(inventoryBytes),summary,rows,dispatch_authorized:false},null,2),{mode:0o600});
  console.log(JSON.stringify(summary));
}
