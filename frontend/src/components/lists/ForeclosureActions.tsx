import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { apiFetch } from '@/lib/api';
import { useProfile } from '@/hooks/useProfile';
import { Button } from '@/components/ui/button';
import { type Review } from './ReviewControl';
type Notice = Review & { county: string; first_seen_at: string; new_today: boolean; indexed_address: string | null; filed_date: string | null; auction_date: string | null };
type Actions = { day: string; total: number; new_today: number; backlog: number; items: Notice[] };
export function ForeclosureActions({ compact = false }: { compact?: boolean }) {
 const { isAdmin, profile } = useProfile();
 const [county, setCounty] = useState('');
 const [offset, setOffset] = useState(0);
 const query = useQuery<Actions>({ queryKey: ['foreclosure-actions', profile?.id, county, offset], enabled: isAdmin,
  refetchInterval: 60000,
  queryFn: async () => (await apiFetch(`/api/operations/lists/foreclosures?offset=${offset}${county ? `&county=${county}` : ''}`)).json() });
 if (!isAdmin) return null;
 return <section aria-label="Foreclosure action items" className="rounded-xl border-2 border-amber-400 bg-amber-50 p-5 space-y-3">
  <h2 className="text-xl font-bold">High Priority Action Items — Foreclosures</h2>
  <p>Dallas and Collin · New to WholesaleOS today · Central time</p>
  <p className="text-sm">New notices need property and current-sale verification before skip-tracing or outreach. High priority means review today; it does not confirm a qualified contact.</p>
  {query.isLoading && <p>Loading foreclosure actions…</p>}
  {query.error && <p role="alert">Foreclosure actions could not be loaded. <Button onClick={() => query.refetch()}>Retry foreclosure actions</Button></p>}
  {query.data && <>
   <p className="font-semibold">{query.data.day}: {query.data.new_today} new notices to review · {query.data.backlog} earlier notices awaiting review</p>
   {compact ? <Link className="underline font-semibold" to="/daily-lists">Review foreclosure action items</Link> : <>
    <label>County <select aria-label="Foreclosure county" value={county} onChange={e => {setCounty(e.target.value);setOffset(0);}} className="rounded border bg-white p-2"><option value="">Dallas and Collin</option><option>Dallas</option><option>Collin</option></select></label>
    {query.data.total === 0 && <p>No notices awaiting review in this view. Check run receipts below for collection status.</p>}
    {query.data.items.map(item => <details className="rounded border bg-white p-3" key={`${item.source_key}:${item.source_record_id}`}>
     <summary className="cursor-pointer"><strong>{item.new_today ? 'HIGH PRIORITY · NEW TODAY' : 'FOLLOW UP · REVIEW PENDING'}</strong> · {item.county} · Notice {item.source_record_id}<br />{item.indexed_address || item.property_address || 'Property not yet verified'}</summary>
     <p className="my-2 text-sm">Filed: {item.filed_date || 'unverified'} · Indexed sale: {item.auction_date || 'unverified'} · Current sale status unverified. Indexed addresses may cover multiple properties.</p>
     <p className="text-sm">On hold until property identity and current sale status are verified. No tracing order or outreach is authorized by this notice.</p>
    </details>)}
    <div className="flex gap-3"><Button disabled={offset === 0} onClick={() => setOffset(Math.max(0,offset-50))}>Previous notices</Button><span>{query.data.total ? offset+1 : 0}–{Math.min(offset+50,query.data.total)} of {query.data.total}</span><Button disabled={offset+50 >= query.data.total} onClick={() => setOffset(offset+50)}>Next notices</Button></div>
   </>}
  </>}
 </section>;
}
