import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { BUYER_CHANGE_EVENT, buyerChangeMessage, pendingBuyerChange, recoverBuyerChange, type PendingBuyerChange } from '@/lib/buyerChanges';

export function BuyerChangeRecovery() {
  const [pending, setPending] = useState<PendingBuyerChange | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const lock = useRef(false);
  const qc = useQueryClient();
  useEffect(() => {
    let active = true; let generation = 0;
    const load = () => { const version = ++generation; void pendingBuyerChange().then(value => { if (active && version === generation) setPending(value); })
      .catch(() => { if (active && version === generation) setMessage('Buyer change recovery is unavailable. Sign in again before another change.'); }); };
    load(); window.addEventListener(BUYER_CHANGE_EVENT, load);
    return () => { active = false; window.removeEventListener(BUYER_CHANGE_EVENT, load); };
  }, []);
  async function recover(action: 'check' | 'retry' | 'cancel') {
    if (lock.current) return; lock.current = true; setBusy(true);
    try {
      const receipt = await recoverBuyerChange(action);
      setMessage(receipt ? `${buyerChangeMessage(receipt.state)} Checking status does not stop the original request.` : 'No saved buyer change is pending for this operator.');
      if (receipt && receipt.state !== 'pending') { setPending(null); void qc.invalidateQueries({queryKey:['buyers']}); }
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Buyer change outcome unconfirmed'); }
    finally { lock.current = false; setBusy(false); }
  }
  if (!pending && !message) return null;
  return <section aria-label="Recover buyer change" className="space-y-2 rounded border border-amber-200 bg-amber-50 p-3 text-sm">
    {pending && <>
      <p>Unconfirmed {pending.kind === 'delete' ? 'deletion' : 'edit'} for {String(pending.expected.first_name ?? '')} {String(pending.expected.last_name ?? '')}. Keep the original reference: {pending.request_id}.</p>
      <p>The original change is locked. Check its result, retry those exact details, or stop a request that has not committed. Stopping does not undo a completed change.</p>
      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={busy} onClick={() => void recover('check')}>Check buyer change</Button>
        <Button size="sm" disabled={busy} onClick={() => void recover('retry')}>Retry original buyer change</Button>
        <Button size="sm" variant="outline" disabled={busy} onClick={() => void recover('cancel')}>Stop pending buyer change</Button>
      </div>
    </>}
    {message && <p role="status">{message}</p>}
  </section>;
}
