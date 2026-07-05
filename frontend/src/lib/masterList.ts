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
  'owner_first_name', 'owner_last_name',
  'owner_phone_1', 'owner_phone_2', 'owner_phone_3', 'owner_email',
  'owner_mailing_address',
  'property_type', 'bedrooms', 'bathrooms', 'sqft', 'year_built', 'asking_price',
] as const;

export type CanonicalField = (typeof CANONICAL_FIELDS)[number];

export const FIELD_LABELS: Record<CanonicalField, string> = {
  property_address: 'Property Address',
  city: 'City',
  state: 'State',
  zip_code: 'Zip',
  owner_first_name: 'Owner First Name',
  owner_last_name: 'Owner Last Name',
  owner_phone_1: 'Phone 1',
  owner_phone_2: 'Phone 2 (skip trace)',
  owner_phone_3: 'Phone 3 (skip trace)',
  owner_email: 'Email',
  owner_mailing_address: 'Mailing Address',
  property_type: 'Property Type',
  bedrooms: 'Bedrooms',
  bathrooms: 'Bathrooms',
  sqft: 'SqFt',
  year_built: 'Year Built',
  asking_price: 'Asking Price',
};

export type MergedRow = {
  [K in CanonicalField]: string;
} & {
  /** Which source lists this address appeared on */
  sources: string[];
  /** How many of the dropped lists contained this address — the "stack" */
  stack_count: number;
};

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

/**
 * Split a combined "123 Main St, Dallas, TX 75201" string into parts. Used when
 * Claude flags a list's address column as containing the whole address inline
 * (common in county rolls). Best-effort — returns whatever it can parse.
 */
export function parseCombinedAddress(raw: string): { street: string; city: string; state: string; zip: string } {
  const original = (raw || '').trim();
  let rest = original;

  const zip = (rest.match(/\b(\d{5})(?:-\d{4})?\s*$/) || [])[1] || '';
  rest = rest.replace(/\b\d{5}(?:-\d{4})?\s*$/, '').trim().replace(/,\s*$/, '');

  // Only treat a trailing 2-letter token as a state if it's anchored by a comma,
  // or a zip was present (structured tail). Prevents "...Address" → state "SS".
  const stateMatch = rest.match(/,\s*([A-Za-z]{2})\s*$/) || (zip ? rest.match(/\s+([A-Za-z]{2})\s*$/) : null);
  let state = '';
  if (stateMatch) {
    state = stateMatch[1].toUpperCase();
    rest = rest.slice(0, stateMatch.index).trim().replace(/,\s*$/, '');
  }

  const parts = rest.split(',').map((s) => s.trim()).filter(Boolean);
  let street = '';
  let city = '';
  if (parts.length >= 2) {
    city = parts[parts.length - 1];
    street = parts.slice(0, parts.length - 1).join(', ');
  } else {
    street = parts[0] || original;
  }
  return { street, city, state, zip };
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
function normalizeField(field: CanonicalField, value: string): string {
  const v = (value || '').trim();
  if (!v) return '';
  if (field === 'state') return v.toUpperCase().slice(0, 2);
  if (field === 'zip_code') return normalizeZip(v);
  if (field === 'owner_phone_1' || field === 'owner_phone_2' || field === 'owner_phone_3') {
    return v.replace(/[^\d+]/g, '');
  }
  return v;
}

export function mergeRowInto(
  acc: Map<string, MergedRow>,
  raw: Record<string, string>,
  sourceLabel: string,
): void {
  const address = (raw.property_address || '').trim();
  if (!address) return; // unusable without an address

  // Build the incoming row field-by-field so every canonical field (including
  // skip-trace phones/mailing address) is carried through automatically.
  const incoming = {} as Record<CanonicalField, string>;
  for (const field of CANONICAL_FIELDS) {
    incoming[field] = normalizeField(field, raw[field] ?? '');
  }

  const key = dedupeKey({ property_address: incoming.property_address, zip_code: incoming.zip_code });
  const existing = acc.get(key);

  if (!existing) {
    acc.set(key, { ...incoming, sources: [sourceLabel], stack_count: 1 });
    return;
  }

  // Duplicate — fill any blank field from the new row (so skip-trace data on
  // one list backfills a property that came from another), keep the more
  // complete values, and count this as an additional stack hit (once per list).
  const merged = { ...existing } as MergedRow;
  for (const field of CANONICAL_FIELDS) {
    merged[field] = firstNonEmpty(existing[field], incoming[field]);
  }
  if (!existing.sources.includes(sourceLabel)) {
    merged.sources = [...existing.sources, sourceLabel];
    merged.stack_count = existing.stack_count + 1;
  }
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
  // Phones are numbered so multiple skip-trace phone columns land in _1/_2/_3
  const phones: number[] = [];
  headers.forEach((h, i) => {
    const n = h.toLowerCase().replace(/[^a-z0-9]/g, '_');
    if (!map.property_address && (n.includes('situs') || n.includes('property_address') || n.includes('parcel_addr') || (n.includes('address') && !n.includes('mail') && !n.includes('owner')))) map.property_address = i;
    if (!map.owner_mailing_address && (n.includes('mail') && n.includes('addr'))) map.owner_mailing_address = i;
    if (!map.city && (n.includes('city') || n.includes('muni'))) map.city = i;
    if (!map.state && (n === 'state' || n.endsWith('_state') || n.includes('_st'))) map.state = i;
    if (!map.zip_code && (n.includes('zip') || n.includes('postal'))) map.zip_code = i;
    if (!map.owner_first_name && (n.includes('first_name') || n.includes('owner_1_first'))) map.owner_first_name = i;
    if (!map.owner_last_name && (n.includes('last_name') || n.includes('owner_1_last') || n.includes('surname'))) map.owner_last_name = i;
    if ((n.includes('phone') || n.includes('mobile') || n.includes('cell')) && phones.length < 3) phones.push(i);
    if (!map.owner_email && n.includes('email')) map.owner_email = i;
    if (!map.property_type && (n.includes('property_type') || n.includes('prop_type') || n.includes('land_use'))) map.property_type = i;
    if (!map.bedrooms && (n.includes('bed') || n === 'br')) map.bedrooms = i;
    if (!map.bathrooms && (n.includes('bath') || n === 'ba')) map.bathrooms = i;
    if (!map.sqft && (n.includes('sqft') || n.includes('sq_ft') || n.includes('square_feet') || n.includes('living_area'))) map.sqft = i;
    if (!map.year_built && (n.includes('year_built') || n.includes('yr_built') || n === 'yearbuilt')) map.year_built = i;
    if (!map.asking_price && (n.includes('asking') || n.includes('list_price') || n === 'price')) map.asking_price = i;
  });
  if (phones[0] !== undefined) map.owner_phone_1 = phones[0];
  if (phones[1] !== undefined) map.owner_phone_2 = phones[1];
  if (phones[2] !== undefined) map.owner_phone_3 = phones[2];
  return map as Record<CanonicalField, number>;
}
