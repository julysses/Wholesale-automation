import type { PendingDeal } from '@/lib/dealWrites';
export function DealRecoveryPanel({pending,busy,retry}:{pending:PendingDeal|null;busy:boolean;retry:()=>void}) {
  if (!pending) return null;
  return <section aria-label="Pending deal recovery" className="border border-amber-300 bg-amber-50 p-3 rounded space-y-2">
    <p>An unconfirmed deal save is pending: {pending.deal.deal_name} · lead {pending.deal.lead_id} · reference {pending.request_id}.</p>
    <p>Recover this exact save before creating another deal. The original inputs will be reused.</p>
    <button disabled={busy} onClick={retry} className="text-blue-700 underline">Recover pending deal</button>
  </section>;
}
