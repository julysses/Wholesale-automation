import { buyerPropertyTypes, buyerStrategies, type BuyerDetails, type BuyerAmounts } from '@/lib/acquisition/buyers';
const input = 'block w-full min-w-0 rounded-lg border border-gray-300 bg-white p-2';
export function BuyerDetailsFields({ details, amounts, zips, onChange, onAmounts, onZips, disabled }: {
  details: BuyerDetails; amounts: BuyerAmounts; zips: string; onChange: (v: BuyerDetails) => void;
  onAmounts: (v: BuyerAmounts) => void; onZips: (v: string) => void; disabled: boolean;
}) {
  const update = <K extends keyof BuyerDetails>(key: K, value: BuyerDetails[K]) => onChange({ ...details, [key]: value });
  return <fieldset disabled={disabled} className="space-y-4 min-w-0"><legend className="font-semibold mb-3">2. Enter buyer details</legend>
    <p className="text-sm text-gray-600">Record what the buyer reported. Leave unknown preferences and budgets blank. These details still need verification.</p>
    <div className="grid gap-3 sm:grid-cols-2">
      {(['first_name', 'last_name', 'company', 'email', 'phone'] as const).map(key => <label key={key} className="block text-sm">{{ first_name: 'First name', last_name: 'Last name', company: 'Company (optional)', email: 'Email (optional)', phone: 'Phone with country code (optional)' }[key]}
        <input className={input} type={key === 'email' ? 'email' : key === 'phone' ? 'tel' : 'text'} value={details[key] ?? ''}
          maxLength={key === 'company' ? 160 : key === 'email' ? 320 : key === 'phone' ? 16 : 120}
          onChange={e => update(key, e.target.value)} /></label>)}
      <label className="block text-sm">Target ZIP codes<input className={input} value={zips} maxLength={700} onChange={e => onZips(e.target.value)} /><span className="text-xs text-gray-500">Separate five-digit ZIP codes with commas.</span></label>
    </div>
    <fieldset className="flex flex-wrap gap-3"><legend className="text-sm font-medium mb-2">Property types</legend>{Object.entries(buyerPropertyTypes).map(([key, label]) => {
      const value = key as BuyerDetails['property_types'][number];
      return <label key={key} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={details.property_types.includes(value)} onChange={e => update('property_types', e.target.checked ? [...details.property_types, value] : details.property_types.filter(v => v !== value))} />{label}</label>;
    })}</fieldset>
    <fieldset className="flex flex-wrap gap-3"><legend className="text-sm font-medium mb-2">Investment strategies</legend>{Object.entries(buyerStrategies).map(([key, label]) => {
      const value = key as BuyerDetails['strategies'][number];
      return <label key={key} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={details.strategies.includes(value)} onChange={e => update('strategies', e.target.checked ? [...details.strategies, value] : details.strategies.filter(v => v !== value))} />{label}</label>;
    })}</fieldset>
    <div className="grid gap-3 sm:grid-cols-2">{Object.entries({ min_price_cents: 'Minimum price ($)', max_price_cents: 'Maximum price ($)', max_repairs_cents: 'Maximum repairs ($)', close_speed_days: 'Reported closing time (days)' }).map(([key, label]) => <label key={key} className="block text-sm">{label}
      <input className={input} inputMode={key === 'close_speed_days' ? 'numeric' : 'decimal'} value={amounts[key as keyof BuyerAmounts]} maxLength={16} onChange={e => onAmounts({ ...amounts, [key]: e.target.value })} placeholder="Unknown" /></label>)}</div>
    <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={details.active} onChange={e => update('active', e.target.checked)} />Keep profile active for future review</label>
    <label className="block text-sm">Source and context<textarea className={input} rows={3} maxLength={2000} value={details.source_note} onChange={e => update('source_note', e.target.value)} /><span className="text-xs text-gray-500">At least 20 characters. Explain where these details came from and what remains unconfirmed.</span></label>
  </fieldset>;
}
export function BuyerDetailsSummary({ details }: { details: BuyerDetails }) {
  const dollars = (value: number | null) => value === null ? 'Unknown' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(value / 100);
  return <div className="space-y-2 rounded-lg border bg-white p-3 text-sm break-words min-w-0">
    <p className="font-semibold">{details.first_name} {details.last_name}{details.company ? ` · ${details.company}` : ''}</p>
    <p>Email: {details.email ?? 'Unknown'} · Phone: {details.phone ?? 'Unknown'}</p>
    <p>Target ZIP codes: {details.target_zips.join(', ') || 'Unknown'}</p>
    <p>Property types: {details.property_types.map(v => buyerPropertyTypes[v]).join(', ') || 'Unknown'}</p>
    <p>Strategies: {details.strategies.map(v => buyerStrategies[v]).join(', ') || 'Unknown'}</p>
    <p>Minimum price: {dollars(details.min_price_cents)} · Maximum price: {dollars(details.max_price_cents)}</p>
    <p>Maximum repairs: {dollars(details.max_repairs_cents)} · Reported closing time: {details.close_speed_days === null ? 'Unknown' : `${details.close_speed_days} days`}</p>
    <p>Status: {details.active ? 'Active for review' : 'Inactive'}</p><p>{details.source_note}</p>
    <p className="font-medium text-amber-800">Self-reported · Buyer verification pending</p>
  </div>;
}
