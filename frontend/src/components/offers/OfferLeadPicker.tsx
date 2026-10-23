import { useState } from 'react';
import { useLeads } from '@/hooks/useLeads';
import { OfferReview } from './OfferReview';

export function OfferLeadPicker() {
 const [search,setSearch]=useState('');
 const [page,setPage]=useState(1);
 const [selected,setSelected]=useState<{id:string;address:string}|null>(null);
 const {data,isLoading,error,refetch}=useLeads({search,page,pageSize:50});
 const rows=data?.data??[];
 const pages=Math.max(1,Math.ceil((data?.count??0)/50));
 return <div className="space-y-3">
  <label>Find offer lead<input className="block w-full rounded border px-3 py-2" aria-label="Find offer lead" value={search} onChange={e=>{setSearch(e.target.value);setPage(1);}} placeholder="Address, owner or phone"/></label>
  {error&&<p role="alert">Unable to load leads: {error.message} <button type="button" onClick={()=>void refetch()}>Retry lead search</button></p>}
  <label>Offer lead<select className="block w-full rounded border px-3 py-2" aria-label="Offer lead" disabled={isLoading||!!error} value={selected?.id??''} onChange={e=>{
   const lead=rows.find(row=>row.id===e.target.value);
   setSelected(lead?{id:lead.id,address:lead.property_address}:null);
  }}>
   <option value="">{isLoading?'Loading leads…':'Choose a lead...'}</option>
   {selected&&!rows.some(row=>row.id===selected.id)&&<option value={selected.id}>{selected.address} (selected)</option>}
   {rows.map(lead=><option key={lead.id} value={lead.id}>{lead.property_address}, {lead.city}</option>)}
  </select></label>
  <div className="flex items-center gap-3">
   <button type="button" disabled={isLoading||page===1} onClick={()=>setPage(p=>p-1)}>Previous offer leads</button>
   <span>Page {page} of {pages}</span>
   <button type="button" disabled={isLoading||!!error||page>=pages} onClick={()=>setPage(p=>p+1)}>Next offer leads</button>
  </div>
  {selected&&<><p>Reviewing {selected.address}</p><OfferReview key={selected.id} leadId={selected.id}/></>}
 </div>;
}
