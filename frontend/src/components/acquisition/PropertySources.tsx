import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/lib/api';

type Touch = { source_id: string; original_lead_id: string; association: 'original_lead' | 'reviewed_property' | 'reviewed_repeat_inquiry'; identity_review_id: string | null; attribution_status: string; attribution_current: boolean; current_campaign_id: string | null; captured_attribution: { id: string; campaign_id: string; link_review_id: string; created_at: string } | null };
type Page = { workspace_id: string; canonical_lead_id: string; property_id: string; items: Touch[]; next_after: string | null; scanned_count: number; excluded_count: number; checked_at: string; count_scope: string; totals_available: false; ownership_verified: false; contact_permission_granted: false; execution_authorized: false };
const uuid = (value: unknown): value is string => typeof value === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value);
const statuses: Record<string, string> = { current_captured_attribution: 'Current attribution', current_review_not_captured: 'Current review has no captured attribution', campaign_review_not_current: 'Campaign review is not current', campaign_evidence_unavailable: 'Campaign evidence unavailable' };
const associations = { original_lead: 'Original inquiry', reviewed_property: 'Reviewed property association', reviewed_repeat_inquiry: 'Reviewed repeat inquiry' };
const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';

export function PropertySources({ userId, workspace, lead, property }: { userId: string; workspace: string; lead: string; property: string }) {
  const [open, setOpen] = useState(false);
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const after = cursors.at(-1) ?? null;
  const page = useQuery({ queryKey: ['property-sources', userId, workspace, lead, property, after], enabled: open, retry: false, gcTime: 0, staleTime: 0, refetchOnWindowFocus: false,
    queryFn: async ({ signal }): Promise<Page> => {
      const value = await (await apiFetch(`/api/acquisition/workspaces/${workspace}/leads/${lead}/source-touches?limit=20${after ? `&after=${after}` : ''}`, { signal })).json() as Page;
      const validTouch = (row: Touch) => row && uuid(row.source_id) && uuid(row.original_lead_id) && Object.hasOwn(associations, row.association)
        && (row.association === 'original_lead' ? row.original_lead_id === lead && row.identity_review_id === null : row.original_lead_id !== lead && uuid(row.identity_review_id))
        && Object.hasOwn(statuses, row.attribution_status) && typeof row.attribution_current === 'boolean'
        && row.attribution_current === (row.attribution_status === 'current_captured_attribution')
        && (row.captured_attribution === null || uuid(row.captured_attribution.id) && uuid(row.captured_attribution.campaign_id) && uuid(row.captured_attribution.link_review_id) && typeof row.captured_attribution.created_at === 'string')
        && (row.attribution_current ? uuid(row.current_campaign_id) && row.current_campaign_id === row.captured_attribution?.campaign_id : row.current_campaign_id === null);
      if (!value || value.workspace_id !== workspace || value.canonical_lead_id !== lead || value.property_id !== property
        || value.count_scope !== 'bounded_candidate_page' || value.totals_available !== false || value.ownership_verified !== false || value.contact_permission_granted !== false || value.execution_authorized !== false
        || !Number.isInteger(value.scanned_count) || value.scanned_count < 0 || value.scanned_count > 20 || !Number.isInteger(value.excluded_count) || value.excluded_count < 0
        || !Array.isArray(value.items) || value.items.length + value.excluded_count !== value.scanned_count || !value.items.every(validTouch)
        || value.items.some((row, i) => (after !== null && row.source_id <= after) || (i > 0 && row.source_id <= value.items[i - 1].source_id))
        || !(value.next_after === null || uuid(value.next_after) && value.scanned_count === 20 && (after === null || value.next_after > after) && value.items.every(row => row.source_id <= value.next_after!))
        || typeof value.checked_at !== 'string' || !Number.isFinite(Date.parse(value.checked_at))) throw new Error('Invalid property source response');
      return value;
    } });
  return <section aria-label="Property inquiry sources" className="border rounded-lg p-3 space-y-3">
    <button className={button} aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? 'Hide property inquiry sources' : 'View property inquiry sources'}</button>
    {open && <><p className="text-sm">Separate inquiries associated with this property. These are not unique seller or conversion totals. Ownership and contact permission require separate review.</p>
      {page.isFetching ? <p role="status">Checking property sources…</p> : page.isError ? <p role="alert">Property sources unavailable. Refresh and verify workspace access.</p> : page.data && <>
        <p className="text-xs">Checked: {page.data.checked_at}. Each page reflects its own review state.</p>
        <ol className="space-y-3">{page.data.items.map(row => <li key={row.source_id} className="border-b py-2 text-sm break-all"><strong>{associations[row.association]}</strong><p>Inquiry: {row.source_id}</p><p>Original lead: {row.original_lead_id}</p><p>{statuses[row.attribution_status]}</p>
          {row.current_campaign_id && <p>Current campaign: {row.current_campaign_id}</p>}
          {row.captured_attribution && !row.attribution_current && <p>Historical attribution: {row.captured_attribution.campaign_id}</p>}
          {row.identity_review_id && <details><summary>Association evidence</summary><p>Identity review: {row.identity_review_id}</p></details>}
        </li>)}</ol>
        {page.data.items.length === 0 && <p>No eligible inquiry touches on this page.</p>}
        {page.data.excluded_count > 0 && <p className="text-sm">{page.data.excluded_count} candidates excluded because their property association is no longer current.</p>}
      </>}
      <nav aria-label="Property source pages" className="flex flex-wrap gap-2"><button className={button} disabled={page.isFetching || cursors.length === 1} onClick={() => setCursors(value => value.slice(0, -1))}>Previous source page</button><button className={button} disabled={page.isFetching || page.isError || !page.data?.next_after} onClick={() => { if (page.data?.next_after) setCursors(value => [...value, page.data!.next_after]); }}>More property sources</button><button className={button} disabled={page.isFetching} onClick={() => { if (after) setCursors([null]); else void page.refetch(); }}>Refresh from first source page</button></nav>
    </>}
  </section>;
}
