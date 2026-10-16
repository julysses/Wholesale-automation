import { useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
type TaxSnapshot = { snapshot_date?: unknown; amount_cents?: unknown; amount_kind?: unknown; review_flags?: unknown; situs_missing?: unknown };
export type Review = { run_id: string; batch_index: number; ordinal: number; source_record_id: string | null; property_address: string | null; source_key: string; review_reason: string; source_url: string; source_fingerprint: string; city: string | null; state: string | null; zip: string | null; parcel_id: string | null; unit: string | null; tax_snapshot?: TaxSnapshot | null };
const taxWarnings: Record<string, string> = {
  active_deferral_review: 'Tax deferral requires review',
  bankruptcy_review: 'Bankruptcy reference requires review',
  legal_proceeding_review: 'Legal proceeding reference requires review',
  payment_status_review: 'Payment arrangement or status requires review',
  duplicate_tax_row_review: 'Duplicate tax rows; aggregate amount withheld',
  unverified_delinquency_date: 'Delinquency date needs verification',
  verify_current_account_status: 'Current account status needs verification',
};
async function action(path: string, method: string, body?: unknown) {
  const response = await apiFetch(path, { method, headers: { 'Content-Type': 'application/json' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  return response.json();
}
export function ReviewControl({ item, refresh }: { item: Review; refresh: () => Promise<unknown> }) {
  const sourceAddress = /^0+$/.test(item.property_address?.trim() ?? '') ? '' : item.property_address ?? '';
  const snapshot = item.tax_snapshot;
  const historicalAmount = typeof snapshot?.amount_cents === 'number' && Number.isSafeInteger(snapshot.amount_cents) && snapshot.amount_cents >= 0
    ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(snapshot.amount_cents / 100) : 'Not available';
  const snapshotDate = typeof snapshot?.snapshot_date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(snapshot.snapshot_date) ? snapshot.snapshot_date : 'Date unavailable';
  const warnings = typeof snapshot?.review_flags === 'string' ? [...new Set(snapshot.review_flags.split(',').filter(Boolean).map(flag => taxWarnings[flag] ?? 'Additional source warning requires review'))] : [];
  const [evidence, setEvidence] = useState('');
  const [leadId, setLeadId] = useState('');
  const [address, setAddress] = useState(sourceAddress);
  const [city, setCity] = useState(item.city ?? '');
  const [zip, setZip] = useState(item.zip ?? '');
  const [parcel, setParcel] = useState(item.parcel_id ?? '');
  const [unit, setUnit] = useState(item.unit ?? '');
  const [notes, setNotes] = useState('');
  const [active, setActive] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState('');
  async function resolve() {
    setPending(true); setMessage('');
    try {
      await action('/api/operations/lists/resolve', 'POST', { run_id: item.run_id, batch_index: item.batch_index, ordinal: item.ordinal,
        county: item.source_key.startsWith('tx-dallas-') ? 'Dallas' : 'Collin', evidence_url: evidence, lead_id: leadId || null, active_signal: active,
        review: { source_fingerprint: item.source_fingerprint, notes: notes.trim(), identity: {
          property_address: address.trim(), city: city.trim(), state: 'TX', zip: zip.trim(), parcel_id: parcel.trim() || null, unit: unit.trim() || null,
        } } });
      await refresh();
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Resolution unconfirmed. Refresh before retrying.'); }
    finally { setPending(false); }
  }
  return <article className="rounded-xl border bg-white p-4 space-y-3">
    <h3 className="font-semibold">{sourceAddress || 'Unresolved property'}</h3>
    <p>{item.source_key} · {item.review_reason.replaceAll('_', ' ')}</p>
    {snapshot && <section aria-label="Historical tax evidence" className="rounded-lg border border-amber-200 bg-amber-50 p-3 space-y-1 text-sm">
      <p className="font-semibold">Historical tax snapshot · {snapshotDate}</p>
      <p>{snapshot.amount_kind === 'remaining_levy' ? 'Recorded remaining levy' : 'Recorded balance'}: {historicalAmount}</p>
      <p>This is not a current payoff or confirmed active delinquency. Verify current account status, ownership scope and any deferral before qualifying this property.</p>
      {(snapshot.situs_missing === true || !sourceAddress) && <p>Property street address is missing from the source.</p>}
      {warnings.map(warning => <p key={warning}>{warning}</p>)}
    </section>}
    <a href={item.source_url} target="_blank" rel="noreferrer" className="underline">Official source record</a>
    <p className="text-sm">Source account or notice: {item.source_record_id}. Confirm the property location in official records; a mailing address does not establish the property location. The original county record stays unchanged.</p>
    <Input label="Verified property street address" value={address} onChange={e => setAddress(e.target.value)} />
    <Input label="Verified property unit, if any" value={unit} onChange={e => setUnit(e.target.value)} />
    <Input label="Verified property city (Texas)" value={city} onChange={e => setCity(e.target.value)} />
    <Input label="Verified property ZIP" value={zip} onChange={e => setZip(e.target.value)} />
    <Input label="Verified parcel ID, if available" value={parcel} onChange={e => setParcel(e.target.value)} />
    <Input label="Evidence notes: explain the account-to-property match and current status" value={notes} onChange={e => setNotes(e.target.value)} />
    <Input label="Official county or title evidence URL" value={evidence} onChange={e => setEvidence(e.target.value)} />
    <Input label="Existing CRM lead UUID, if already present" value={leadId} onChange={e => setLeadId(e.target.value)} />
    <label className="block"><input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} /> I verified the exact property and county; probate evidence establishes title, not just a matching name.</label>
    <label className="block"><input type="checkbox" checked={active} onChange={e => setActive(e.target.checked)} /> The source confirms a currently active distress signal.</label>
    <Button disabled={pending || !confirmed || !evidence || !item.source_record_id || !item.source_fingerprint || !address.trim() || /^0+$/.test(address.trim()) || !city.trim() || !/^\d{5}(-\d{4})?$/.test(zip.trim()) || notes.trim().length < 10} onClick={resolve}>Save verified association</Button>
    {message && <p role="alert" className="text-red-700">{message}</p>}
  </article>;
}
