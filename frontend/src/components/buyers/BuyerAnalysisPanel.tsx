import { useRef, useState } from 'react';
import { z } from 'zod';
import { apiFetch } from '@/lib/api';
import { supabase } from '@/lib/supabase';
import { Button } from '@/components/ui/button';

const draftSchema = z.object({ actor: z.string().min(1), request_id: z.string().uuid(), kind: z.enum(['score', 'classify']),
  buyer_id: z.string().uuid().nullable(), paid_confirmed: z.boolean() }).strict();
type Draft = z.infer<typeof draftSchema>;
const count = z.number().int().nonnegative();
const statusSchema = z.object({ id: z.string().uuid(), state: z.enum(['unconfirmed', 'stopped', 'running', 'review', 'complete']),
  kind: z.enum(['score', 'classify']).optional(), selected_buyer: z.string().uuid().nullable().optional(),
  total: count.optional(), processed: count.optional(), applied: count.optional(), failed: count.optional(), stale: count.optional(),
  missing: count.optional(), unknown: count.optional(), blocked: count.optional(), held: count.optional(), ready: count.optional(), pending: count.optional(),
  can_run: z.boolean().optional(), offset: count.optional(),
  items: z.array(z.object({ buyer_id: z.string().uuid(), name: z.string(), state: z.enum(['applied','failed','unknown','stale','missing','canceled','blocked','ready','unconfirmed','pending']),
    metadata: z.record(z.string(), z.unknown()) })).max(20).optional(),
});
type Status = z.infer<typeof statusSchema>;
async function actor() {
  const { data, error } = await supabase.auth.getSession();
  if (error || !data.session?.user?.id) throw new Error('Sign in as the original operator to recover analysis.');
  return data.session.user.id;
}

export function BuyerAnalysisPanel({ kind, buyerId = null, onUpdated }: {
  kind: 'score' | 'classify'; buyerId?: string | null; onUpdated?: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [paid, setPaid] = useState(false);
  const [configured, setConfigured] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const lock = useRef(false);
  const storageKey = (id: string) => `hilltop.buyer-analysis.v1.${id}.${kind}.${buyerId ?? 'all'}`;
  async function perform(work: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError('');
    try { await work(); } catch (e) {
      setError(e instanceof Error ? e.message : 'Outcome unconfirmed. Check the original reference.');
      setStatus(null); // Uncertain writes never retain an actionable stale receipt.
    } finally { lock.current = false; setBusy(false); }
  }
  async function confirm(response: Response, value: Draft, offset = 0) {
    const receipt = statusSchema.parse(await response.json());
    if (await actor() !== value.actor || receipt.id !== value.request_id
      || (receipt.kind && (receipt.kind !== value.kind || receipt.selected_buyer !== value.buyer_id || receipt.offset !== offset
        || receipt.total === undefined || receipt.processed === undefined || receipt.pending === undefined
        || receipt.applied === undefined || receipt.failed === undefined || receipt.stale === undefined || receipt.missing === undefined
        || receipt.unknown === undefined || receipt.blocked === undefined || receipt.held === undefined || receipt.ready === undefined
        || receipt.can_run === undefined || receipt.items === undefined || receipt.processed + receipt.pending !== receipt.total))) {
      throw new Error('Analysis receipt does not match this request. Keep the original reference.');
    }
    setStatus(receipt);
    if ((receipt.applied ?? 0) > 0) onUpdated?.();
  }
  async function check(value: Draft, offset = 0) {
    if (await actor() !== value.actor) throw new Error('Recover this request as its original operator.');
    await confirm(await apiFetch(`/api/buyers/analysis/${value.request_id}?offset=${offset}`), value, offset);
  }
  async function prepare() {
    setExpanded(true);
    await perform(async () => {
      const id = await actor(); const raw = sessionStorage.getItem(storageKey(id));
      if (raw) {
        const saved = draftSchema.parse(JSON.parse(raw));
        if (saved.actor !== id || saved.kind !== kind || saved.buyer_id !== buyerId
          || (kind === 'classify' && !saved.paid_confirmed)) throw new Error('Saved analysis scope requires review.');
        setDraft(saved); await check(saved);
      }
      if (kind === 'classify') {
        const config = await (await apiFetch('/api/buyers/analysis/config')).json();
        if (typeof config.configured !== 'boolean') throw new Error('AI configuration could not be confirmed.');
        setConfigured(config.configured);
      }
    });
  }
  async function start() {
    await perform(async () => {
      let value = draft;
      if (!value) {
        value = { actor: await actor(), request_id: crypto.randomUUID(), kind, buyer_id: buyerId, paid_confirmed: kind === 'classify' && paid };
        sessionStorage.setItem(storageKey(value.actor), JSON.stringify(value)); // Save before any write; storage errors fail closed.
        setDraft(value);
      }
      if (await actor() !== value.actor) throw new Error('Recover this request as its original operator.');
      const body = { request_id: value.request_id, kind: value.kind, buyer_id: value.buyer_id, paid_confirmed: value.paid_confirmed };
      await confirm(await apiFetch('/api/buyers/analysis/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }), value);
    });
  }
  async function action(actionName: 'run' | 'cancel') {
    const value = draft; if (!value) return;
    await perform(async () => {
      if (await actor() !== value.actor) throw new Error('Recover this request as its original operator.');
      await confirm(await apiFetch(`/api/buyers/analysis/${value.request_id}/${actionName}`, { method: 'POST' }), value);
    });
  }
  return <section className="space-y-2 rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm" aria-label={kind === 'classify' ? 'Buyer AI classification' : 'Buyer rescoring'}>
    <Button variant="outline" size="sm" disabled={busy} onClick={() => void prepare()}>{kind === 'classify' ? 'Prepare AI classification' : 'Prepare re-score'}</Button>
    {expanded && <>
      <p>{kind === 'classify' ? 'One AI attempt sends this buyer profile and up to 10 recent purchases to the configured provider. Usage charges may apply. Suggestions do not establish verified buyer facts.' : 'Re-score the active buyers selected when this request starts, using complete purchase history. Continue in groups of up to 20. No paid AI call.'}</p>
      {kind === 'classify' && !configured && <p>AI provider configuration is unavailable or unconfirmed. Saved results can still be checked.</p>}
      {!draft && kind === 'classify' && <label className="flex gap-2"><input type="checkbox" checked={paid} onChange={e => setPaid(e.target.checked)} />I approve one provider attempt for this buyer and its usage charge.</label>}
      {!draft && <Button size="sm" disabled={busy || (kind === 'classify' && (!paid || !configured))} onClick={() => void start()}>Create analysis request</Button>}
      {draft && <>
        <p className="break-all text-xs">Reference: {draft.request_id}</p>
        <div className="flex flex-wrap gap-2">
          {(!status || status.state === 'unconfirmed') && <Button size="sm" disabled={busy} onClick={() => void start()}>Recover original request</Button>}
          <Button variant="outline" size="sm" disabled={busy} onClick={() => void perform(() => check(draft))}>Check saved status</Button>
          {status?.can_run && <Button size="sm" disabled={busy} onClick={() => void action('run')}>{kind === 'classify' ? (status.ready ? 'Apply saved result' : 'Run one AI classification') : 'Run next 20'}</Button>}
          {!['complete', 'stopped'].includes(status?.state ?? '') && <Button variant="outline" size="sm" disabled={busy} onClick={() => void action('cancel')}>Stop this request</Button>}
          {['complete', 'stopped'].includes(status?.state ?? '') && <Button variant="outline" size="sm" disabled={busy} onClick={() => void perform(async () => {
            if (await actor() !== draft.actor) throw new Error('Recover as the original operator.');
            sessionStorage.removeItem(storageKey(draft.actor)); setDraft(null); setStatus(null); setPaid(false);
          })}>Prepare a new request</Button>}
        </div>
      </>}
      {status && <div role="status">
        <p>Request: {status.state}. {status.total !== undefined && `${status.processed} of ${status.total} processed; ${status.applied} applied, ${status.failed} failed, ${status.stale} changed, ${status.missing} missing.`}</p>
        {(status.unknown ?? 0) + (status.blocked ?? 0) + (status.held ?? 0) > 0 && <p>Some provider outcomes need review. No automatic paid retry will run. Stopping this request does not release an uncertain paid attempt.</p>}
        {status.items?.map(item => <p key={item.buyer_id}>{item.name}: {item.state}{typeof item.metadata.reason === 'string' ? ` — ${item.metadata.reason}` : ''}{typeof item.metadata.reasoning === 'string' ? ` — ${item.metadata.reasoning}` : ''}</p>)}
        {draft && (status.total ?? 0) > 20 && <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={busy || !status.offset} onClick={() => void perform(() => check(draft, Math.max(0, (status.offset ?? 0) - 20)))}>Previous results</Button>
          <Button size="sm" variant="outline" disabled={busy || (status.offset ?? 0) + 20 >= (status.total ?? 0)} onClick={() => void perform(() => check(draft, (status.offset ?? 0) + 20))}>Next results</Button>
        </div>}
      </div>}
      {error && <p role="alert">{error}</p>}
    </>}
  </section>;
}
