import { useCallback, useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { RotateCw, Trash2 } from 'lucide-react';
import { Modal } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import {
  applyCleanup, deleteBuyerImport, deleteLeadList, fetchBuyerImports, fetchCleanupSuggestions, fetchLeadLists, rescoreLeadList,
  type BuyerImport, type CleanupRule, type HoldPolicy, type LeadList,
} from '@/lib/leadLists';

/** One place to see every uploaded lead list / buyer upload, re-score it, or delete it. */
export function ManageListsModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const [lists, setLists] = useState<LeadList[]>([]);
  const [imports, setImports] = useState<BuyerImport[]>([]);
  const [rules, setRules] = useState<CleanupRule[]>([]);
  const [hold, setHold] = useState<HoldPolicy[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [l, b] = await Promise.all([fetchLeadLists(), fetchBuyerImports()]);
      setLists(l); setImports(b); setError(null);
      // Suggestions need the latest migration; never block the lists if they are unavailable.
      fetchCleanupSuggestions().then(c => { setRules(c.rules); setHold(c.hold); }).catch(() => undefined);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load lists');
    }
  }, []);

  useEffect(() => { if (open) void load(); }, [open, load]);

  const run = async (key: string, work: () => Promise<string>) => {
    setBusy(key);
    try {
      toast.success(await work());
      await Promise.all([load(), qc.invalidateQueries({ queryKey: ['leads'] }), qc.invalidateQueries({ queryKey: ['buyers'] })]);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Action failed');
    } finally {
      setBusy(null);
    }
  };

  const removeList = (list: LeadList) => {
    const worked = list.worked_count;
    const includeWorked = worked > 0 && confirm(
      `"${list.name}" has ${worked} lead(s) already being worked (contacted, offers, contracts).\n\n`
      + 'OK = delete those too.   Cancel = keep them and delete only untouched leads.');
    if (!confirm(`Delete ${includeWorked ? list.lead_count : list.deletable_count} lead(s) from "${list.name}"? This cannot be undone.`)) return;
    void run(list.id, async () => {
      const r = await deleteLeadList(list.id, includeWorked);
      return `Deleted ${r.deleted} leads${r.kept_worked ? `; kept ${r.kept_worked} worked` : ''}`;
    });
  };

  return (
    <Modal open={open} onClose={onClose} title="Manage uploaded lists" size="xl">
      {error && <p role="alert" className="text-sm text-red-600 mb-3">{error}</p>}
      <h3 className="text-sm font-semibold text-gray-700 mb-2">Lead lists</h3>
      {lists.length === 0 ? <p className="text-sm text-gray-500 mb-4">No tracked lists yet — new uploads appear here.</p> : (
        <ul className="divide-y border rounded-lg mb-6">
          {lists.map(l => (
            <li key={l.id} className="flex items-center gap-3 p-3">
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{l.name}</p>
                <p className="text-xs text-gray-500">
                  {l.lead_count.toLocaleString()} leads · {l.unscored.toLocaleString()} unscored · {l.worked_count.toLocaleString()} worked ·{' '}
                  {new Date(l.created_at).toLocaleDateString()}
                </p>
              </div>
              <Button size="sm" variant="outline" disabled={busy !== null} icon={<RotateCw className="h-3.5 w-3.5" />}
                onClick={() => void run(l.id, async () => `Re-scored ${(await rescoreLeadList(l.id)).scored} leads`)}>Re-score</Button>
              <Button size="sm" variant="outline" disabled={busy !== null} icon={<Trash2 className="h-3.5 w-3.5" />}
                onClick={() => removeList(l)}>Delete</Button>
            </li>
          ))}
        </ul>
      )}
      <h3 className="text-sm font-semibold text-gray-700 mb-1">Suggested cleanup</h3>
      <p className="text-xs text-gray-500 mb-2">Only leads nobody has contacted are ever deleted. DNC / opted-out leads are never touched.</p>
      {rules.length === 0 ? <p className="text-sm text-gray-500 mb-6">No suggestions available.</p> : (
        <ul className="divide-y border rounded-lg mb-3">
          {rules.map(r => (
            <li key={r.id} className="flex items-start gap-3 p-3">
              <div className="flex-1 min-w-0">
                <p className="font-medium">{r.label} <span className="text-xs font-normal text-gray-500">- {r.action}</span></p>
                <p className="text-xs text-gray-500">{r.why}</p>
              </div>
              <span className="text-sm font-semibold tabular-nums w-16 text-right">{r.count.toLocaleString()}</span>
              <Button size="sm" variant="outline" disabled={busy !== null || r.count === 0} icon={<Trash2 className="h-3.5 w-3.5" />}
                onClick={() => { if (confirm(`Delete ${r.count.toLocaleString()} leads: ${r.label}? This cannot be undone.`))
                  void run(r.id, async () => `Deleted ${(await applyCleanup(r.id)).deleted} leads`); }}>Delete</Button>
            </li>
          ))}
        </ul>
      )}
      {hold.length > 0 && (
        <div className="mb-6 rounded-lg bg-gray-50 border p-3 text-xs text-gray-600 space-y-1">
          <p className="font-semibold text-gray-700">Keep these</p>
          {hold.map(h => <p key={h.who}><span className="font-medium">{h.who}</span> - {h.keep}. {h.why}</p>)}
        </div>
      )}
      <h3 className="text-sm font-semibold text-gray-700 mb-2">Buyer uploads</h3>
      {imports.length === 0 ? <p className="text-sm text-gray-500">No buyer uploads yet.</p> : (
        <ul className="divide-y border rounded-lg">
          {imports.map(b => (
            <li key={b.id} className="flex items-center gap-3 p-3">
              <div className="flex-1 min-w-0">
                <p className="font-medium truncate">{b.filename || 'Buyer upload'}</p>
                <p className="text-xs text-gray-500">
                  {b.buyers_remaining.toLocaleString()} buyers · {b.market || 'no market'} · {new Date(b.created_at).toLocaleDateString()}
                </p>
              </div>
              <Button size="sm" variant="outline" disabled={busy !== null} icon={<Trash2 className="h-3.5 w-3.5" />}
                onClick={() => { if (confirm(`Delete the ${b.buyers_remaining} buyers created by "${b.filename}"? Buyers that existed before this upload are kept.`))
                  void run(b.id, async () => `Deleted ${(await deleteBuyerImport(b.id)).buyers_deleted} buyers`); }}>Delete</Button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  );
}
