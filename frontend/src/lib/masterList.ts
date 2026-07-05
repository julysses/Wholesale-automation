/**
 * masterList — merge engine for the Master List Builder.
 *
 * Takes N parsed CSV lists (any column layout — PropStream, county rolls,
 * XLeads, etc.), each already mapped to canonical fields, and folds them into
 * one deduped master list keyed on normalized address + zip. Rows that appear
 * on multiple source lists are "stacked" — this mirrors the app's own
 * distress-stacking concept, so a property on 3 lists is exactly the kind of
 * high-priority stack the Precision/Hybrid strategies are built around.
 */

export const CANONICAL_FIELDS = [
  'property_address', 'city', 'state', 'zip_code',
  'owner_first_name', 'owner_last_name', 'owner_phone_1', 'owner_email',
  'bedrooms', 'bathrooms', 'sqft', 'asking_price',
] as const;

export type CanonicalField = (typeof CANONICAL_FIELDS)[number];

export const FIELD_LABELS: Record<CanonicalField, string> = {
  property_address: 'Property Address',
  city: 'City',
  state: 'State',
  zip_code: 'Zip',
  owner_first_name: 'Owner First Name',
  owner_last_name: 'Owner Last Name',
  owner_phone_1: 'Phone',
  owner_email: 'Email',
  bedrooms: 'Bedrooms',
  bathrooms: 'Bathrooms',
  sqft: 'SqFt',
  asking_price: 'Asking Price',
};

export interface MergedRow {
  property_address: string;
  city: string;
  state: string;
  zip_code: string;
  owner_first_name: string;
  owner_last_name: string;
  owner_phone_1: string;
  owner_email: string;
  bedrooms: string;
  bathrooms: string;
  sqft: string;
  asking_price: string;
  /** Which source lists this address appeared on */
  sources: string[];
  /** How many of the dropped lists contained this address — the "stack" */
  stack_count: number;
}

// Common street-suffix abbreviations, standardized during dedup matching so
// "123 Main St" and "123 Main Street" collapse to the same key.
const SUFFIX_MAP: Record<string, string> = {
  street: 'st', avenue: 'ave', drive: 'dr', lane: 'ln', road: 'rd',
  court: 'ct', boulevard: 'blvd', place: 'pl', circle: 'cir',
  trail: 'trl', parkway: 'pkwy', highway: 'hwy', terrace: 'ter',
  square: 'sq', loop: 'lp', way: 'way',
};

export function normalizeAddress(raw: string): string {
  let s = (raw || '').toLowerCase().trim();
  s = s.replace(/[.,#]/g, ' ');
  s = s.replace(/\s+/g, ' ');
  const words = s.split(' ').map((w) => SUFFIX_MAP[w] ?? w);
  return words.join(' ').trim();
}

function normalizeZip(raw: string): string {
  return (raw || '').trim().slice(0, 5);
}

/** Dedup key: normalized address + zip. Falls back to address-only if zip is missing
 *  (still catches most PropStream-vs-county duplicates within one target area). */
export function dedupeKey(row: { property_address: string; zip_code: string }): string {
  const addr = normalizeAddress(row.property_address);
  const zip = normalizeZip(row.zip_code);
  return zip ? `${addr}|${zip}` : addr;
}

function firstNonEmpty(...vals: (string | undefined)[]): string {
  for (const v of vals) {
    if (v && v.trim()) return v.trim();
  }
  return '';
}

/**
 * Merge one incoming row into the accumulator map. If the address is new,
 * inserts it. If it's a duplicate, fills any blank fields from the new row
 * and bumps the stack count + source list.
 */
export function mergeRowInto(
  acc: Map<string, MergedRow>,
  raw: Record<string, string>,
  sourceLabel: string,
): void {
  const address = (raw.property_address || '').trim();
  if (!address) return; // unusable without an address

  const incoming: Omit<MergedRow, 'sources' | 'stack_count'> = {
    property_address: address,
    city: (raw.city || '').trim(),
    state: (raw.state || '').trim().toUpperCase().slice(0, 2),
    zip_code: normalizeZip(raw.zip_code || ''),
    owner_first_name: (raw.owner_first_name || '').trim(),
    owner_last_name: (raw.owner_last_name || '').trim(),
    owner_phone_1: (raw.owner_phone_1 || '').replace(/[^\d+]/g, ''),
    owner_email: (raw.owner_email || '').trim(),
    bedrooms: (raw.bedrooms || '').trim(),
    bathrooms: (raw.bathrooms || '').trim(),
    sqft: (raw.sqft || '').trim(),
    asking_price: (raw.asking_price || '').trim(),
  };

  const key = dedupeKey(incoming);
  const existing = acc.get(key);

  if (!existing) {
    acc.set(key, { ...incoming, sources: [sourceLabel], stack_count: 1 });
    return;
  }

  // Duplicate — fill gaps from the new row, keep the more complete address,
  // and count this as an additional stack hit (only once per source list).
  const merged: MergedRow = {
    property_address: firstNonEmpty(existing.property_address, incoming.property_address),
    city: firstNonEmpty(existing.city, incoming.city),
    state: firstNonEmpty(existing.state, incoming.state),
    zip_code: firstNonEmpty(existing.zip_code, incoming.zip_code),
    owner_first_name: firstNonEmpty(existing.owner_first_name, incoming.owner_first_name),
    owner_last_name: firstNonEmpty(existing.owner_last_name, incoming.owner_last_name),
    owner_phone_1: firstNonEmpty(existing.owner_phone_1, incoming.owner_phone_1),
    owner_email: firstNonEmpty(existing.owner_email, incoming.owner_email),
    bedrooms: firstNonEmpty(existing.bedrooms, incoming.bedrooms),
    bathrooms: firstNonEmpty(existing.bathrooms, incoming.bathrooms),
    sqft: firstNonEmpty(existing.sqft, incoming.sqft),
    asking_price: firstNonEmpty(existing.asking_price, incoming.asking_price),
    sources: existing.sources.includes(sourceLabel) ? existing.sources : [...existing.sources, sourceLabel],
    stack_count: existing.sources.includes(sourceLabel) ? existing.stack_count : existing.stack_count + 1,
  };
  acc.set(key, merged);
}

export function toCSV(rows: MergedRow[]): string {
  const headers = [...CANONICAL_FIELDS, 'source', 'stack_count'];
  const escape = (v: unknown) => {
    const s = v == null ? '' : String(v);
    return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [headers.join(',')];
  for (const r of rows) {
    const values = [
      ...CANONICAL_FIELDS.map((f) => r[f]),
      r.sources.join(' | '),
      r.stack_count,
    ];
    lines.push(values.map(escape).join(','));
  }
  return lines.join('\n');
}

export function downloadCSV(filename: string, csv: string): void {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

/** Cheap offline fallback mapper — used if the Claude column-mapping call
 *  fails (no API key, network) so the tool still works without it. */
export function heuristicMapColumns(headers: string[]): Record<CanonicalField, number> {
  const map: Partial<Record<CanonicalField, number>> = {};
  headers.forEach((h, i) => {
    const n = h.toLowerCase().replace(/[^a-z0-9]/g, '_');
    if (!map.property_address && (n.includes('situs') || n.includes('property_address') || (n.includes('address') && !n.includes('mail') && !n.includes('owner')))) map.property_address = i;
    if (!map.city && n.includes('city')) map.city = i;
    if (!map.state && (n === 'state' || n.endsWith('_state'))) map.state = i;
    if (!map.zip_code && n.includes('zip')) map.zip_code = i;
    if (!map.owner_first_name && (n.includes('first_name') || n.includes('owner_1_first'))) map.owner_first_name = i;
    if (!map.owner_last_name && (n.includes('last_name') || n.includes('owner_1_last'))) map.owner_last_name = i;
    if (!map.owner_phone_1 && n.includes('phone')) map.owner_phone_1 = i;
    if (!map.owner_email && n.includes('email')) map.owner_email = i;
    if (!map.bedrooms && (n.includes('bed') || n === 'br')) map.bedrooms = i;
    if (!map.bathrooms && (n.includes('bath') || n === 'ba')) map.bathrooms = i;
    if (!map.sqft && (n.includes('sqft') || n.includes('sq_ft') || n.includes('square_feet'))) map.sqft = i;
    if (!map.asking_price && (n.includes('asking') || n.includes('list_price') || n === 'price')) map.asking_price = i;
  });
  return map as Record<CanonicalField, number>;
}
