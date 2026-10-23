import { useEffect, useState } from 'react';
import { readOfferHistory, type OfferHistoryPage } from '@/lib/offerReview';

export function OfferHistory({lead}:{lead:string}) {
 const [events,setEvents]=useState<OfferHistoryPage['events']>([]);
 const [cursor,setCursor]=useState<number|null>(null);
 const [loaded,setLoaded]=useState(false);
 const [busy,setBusy]=useState(true);
 const [error,setError]=useState('');
 useEffect(()=>{
  let active=true;
  readOfferHistory(lead).then(page=>{if(active){setEvents(page.events);setCursor(page.next_before);setLoaded(true);}})
   .catch(()=>{if(active)setError('Offer history could not be loaded. Retry to verify the record.');})
   .finally(()=>{if(active)setBusy(false);});
  return ()=>{active=false;};
 },[lead]);
 async function load(){
  setBusy(true);setError('');
  try{const page=await readOfferHistory(lead,loaded?cursor:null);setEvents(old=>loaded?[...old,...page.events]:page.events);setCursor(page.next_before);setLoaded(true);}
  catch{setError('Offer history could not be loaded. Retry to verify the record.');}
  finally{setBusy(false);}
 }
 return <section aria-label="Offer decision history" className="space-y-2 rounded border p-3">
  <h3 className="font-semibold">Decision history</h3>
  <p>Historical decisions do not establish current approval. Check the current saved status above.</p>
  {error&&<p role="alert">{error}</p>}
  {busy&&<p>Loading history…</p>}
  {loaded&&!events.length&&<p>No decisions recorded.</p>}
  <ol className="space-y-3">{events.map(event=><li key={event.id}>
   <p>Version {event.expected_version+1}: {event.action==='draft'?'Draft saved':event.action==='approve'?'Approval recorded':'Approval revoked'}</p>
   <p>Operator: {event.operator_id} · {event.created_at}</p>
   <p className="break-all">Revision: {event.revision_id}</p>
   {event.terms&&<details><summary>View saved terms</summary><p>${event.terms.price} · Closing {event.terms.closing_date} · Expires {event.terms.expires_at}</p><p>{event.terms.recipient} / {event.terms.channel}</p><p className="whitespace-pre-wrap">{event.terms.conditions}</p></details>}
  </li>)}</ol>
  {(error||cursor!==null)&&<button type="button" disabled={busy} onClick={()=>void load()} className="rounded border px-3 py-2 disabled:opacity-50">{error?'Retry history':'Load older decisions'}</button>}
 </section>;
}
