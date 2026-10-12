import { OfferHistory } from './OfferHistory';
import { useEffect, useState } from 'react';
import { useProfile } from '@/hooks/useProfile';
import { pendingOffer, readOffer, writeOffer, type OfferDecision, type OfferSnapshot, type OfferTerms } from '@/lib/offerReview';

const empty:OfferTerms={price:'',closing_date:'',expires_at:'',recipient:'',channel:'manual',conditions:''};
export function OfferReview({leadId}:{leadId:string}) {
 const {profile,isAdmin,loading,error}=useProfile();
 if(loading)return <p>Checking review access…</p>;
 if(error)return <p role="alert">{error}</p>;
 if(!isAdmin || !profile)return <p>Offer approval requires an approved administrator.</p>;
 return <Review key={`${profile.id}:${leadId}`} actor={profile.id} lead={leadId}/>;
}
function Review({actor,lead}:{actor:string;lead:string}) {
 const [snapshot,setSnapshot]=useState<OfferSnapshot|null>(null);
 const [terms,setTerms]=useState<OfferTerms>(empty);
 const [pending,setPending]=useState<OfferDecision|null>(null);
 const [busy,setBusy]=useState(true);
 const [error,setError]=useState('');
 const [notice,setNotice]=useState('');
 const [confirmed,setConfirmed]=useState(false);
 const [now,setNow]=useState(Date.now);
 useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return ()=>clearInterval(timer);},[]);
 const accept=(value:OfferSnapshot)=>{setSnapshot(value);setTerms(value.revision?.terms??empty);setConfirmed(false);};
 useEffect(()=>{
  let active=true;
  async function load(){
   try {const saved=pendingOffer(actor,lead);const current=await readOffer(lead);if(active){setPending(saved);accept(current);}}
   catch(e){if(active)setError(e instanceof Error?e.message:'Review could not be loaded');}
   finally{if(active)setBusy(false);}
  }
  void load();return ()=>{active=false;};
 },[actor,lead]);
 const refresh=async()=>{
  setBusy(true);setError('');setNotice('');setConfirmed(false);
  try{setPending(pendingOffer(actor,lead));accept(await readOffer(lead));}
  catch(e){setSnapshot(null);setError(e instanceof Error?e.message:'Readback failed');}
  finally{setBusy(false);}
 };
 const submit=async(action:OfferDecision['action'])=>{
  if(!snapshot || busy)return;
  setBusy(true);setError('');setNotice('');setConfirmed(false);
  try {
   let decision=pending;
   if(!decision){
    const id=crypto.randomUUID();
    if(action==='draft'){
     if(!/^\d+(\.\d{1,2})?$/.test(terms.price)||Number(terms.price)<=0||Number(terms.price)>100000000||!terms.closing_date||!terms.recipient.trim()||!terms.conditions.trim()||(!/(Z|[+-]\d{2}:\d{2})$/.test(terms.expires_at)||!Number.isFinite(Date.parse(terms.expires_at))))throw new Error('Enter a positive price, closing date, expiry, recipient and conditions.');
     decision={request_id:id,revision_id:id,expected_version:snapshot.version,action,terms:{...terms,expires_at:new Date(terms.expires_at).toISOString()}};
    }else{
     if(!snapshot.revision)throw new Error('Save terms before making a decision.');
     decision={request_id:id,revision_id:snapshot.revision.id,expected_version:snapshot.version,action};
    }
   }
   setPending(decision);
   const current=await writeOffer(actor,lead,decision);
   accept(current);setPending(null);setNotice('Decision recorded. Current saved status is shown below. Nothing was sent.');
  }catch(e){
   try{setPending(pendingOffer(actor,lead));}catch{setError('Recovery data is unreadable. Do not submit another decision; review the saved record.');setSnapshot(null);return;}
   setError(e instanceof Error?e.message:'Decision is unconfirmed');
   setConfirmed(false);
  }finally{setBusy(false);}
 };
 const saved=snapshot?.revision?.terms;
 const dirty=JSON.stringify(terms)!==JSON.stringify(saved??empty);
 const expired=saved ? Date.parse(saved.expires_at)<=now : false;
 const canDecide=!!saved&&!busy&&!pending&&!error&&!dirty&&!expired;
 return <section className="space-y-3" aria-label="Human offer review">
  <p>Save exact terms, review the saved record, then approve. This screen never sends an offer.</p>
  {error&&<p role="alert" className="text-red-700">{error}</p>}
  {notice&&<p role="status">{notice}</p>}
  <button className="rounded border px-3 py-2 disabled:opacity-50" type="button" onClick={()=>void refresh()} disabled={busy}>Refresh saved record</button>
  {pending&&<div role="alert"><p>An unconfirmed {pending.action} is pending. Reference: {pending.request_id}. Recover it before editing.</p><button className="rounded border px-3 py-2 disabled:opacity-50" type="button" disabled={busy||!snapshot} onClick={()=>void submit(pending.action)}>Retry exact decision</button></div>}
  {snapshot&&<>
   <p>Review version {snapshot.version} · {snapshot.approved&&!expired?'Approved':expired?'Expired':'Not approved'}</p>
   {saved&&<dl className="rounded border p-3 space-y-1">
    <dt>Saved price</dt><dd>${saved.price}</dd><dt>Closing date</dt><dd>{saved.closing_date}</dd>
    <dt>Expires</dt><dd>{saved.expires_at}</dd><dt>Recipient / channel</dt><dd>{saved.recipient} / {saved.channel}</dd>
    <dt>Conditions</dt><dd className="whitespace-pre-wrap">{saved.conditions}</dd>
    <dt>Revision</dt><dd>{snapshot.revision?.id}</dd><dt>Recorded by</dt><dd>{snapshot.revision?.operator_id}</dd>
    {snapshot.approval&&<><dt>Approval recorded by</dt><dd>{snapshot.approval.operator_id} at {snapshot.approval.created_at}</dd></>}
   </dl>}
   <fieldset disabled={busy||!!pending} className="grid gap-2">
    <legend>Human-entered terms</legend>
    <label>Offer price<input className="block w-full rounded border px-3 py-2" aria-label="Offer price" value={terms.price} onChange={e=>{setTerms({...terms,price:e.target.value});setConfirmed(false);}}/></label>
    <label>Closing date<input className="block w-full rounded border px-3 py-2" aria-label="Closing date" type="date" value={terms.closing_date} onChange={e=>{setTerms({...terms,closing_date:e.target.value});setConfirmed(false);}}/></label>
    <label>Expiry (include time zone)<input className="block w-full rounded border px-3 py-2" aria-label="Expiry (include time zone)" placeholder="2026-10-20T17:00:00-05:00" value={terms.expires_at} onChange={e=>{setTerms({...terms,expires_at:e.target.value});setConfirmed(false);}}/></label>
    <label>Recipient<input className="block w-full rounded border px-3 py-2" aria-label="Recipient" value={terms.recipient} onChange={e=>{setTerms({...terms,recipient:e.target.value});setConfirmed(false);}}/></label>
    <label>Intended channel<select className="block w-full rounded border px-3 py-2" aria-label="Intended channel" value={terms.channel} onChange={e=>{setTerms({...terms,channel:e.target.value as OfferTerms['channel']});setConfirmed(false);}}><option value="manual">Manual</option><option value="email">Email</option><option value="sms">SMS</option></select></label>
    <label>Conditions<textarea className="block w-full rounded border px-3 py-2" aria-label="Conditions" value={terms.conditions} onChange={e=>{setTerms({...terms,conditions:e.target.value});setConfirmed(false);}}/></label>
    <button className="rounded border px-3 py-2 disabled:opacity-50" type="button" disabled={!dirty} onClick={()=>void submit('draft')}>Save new revision</button>
   </fieldset>
   {dirty&&saved&&<p>Unsaved edits cannot be approved. Save a new revision or refresh to restore saved terms.</p>}
   <label><input type="checkbox" checked={confirmed} disabled={!canDecide} onChange={e=>setConfirmed(e.target.checked)}/> I reviewed the exact saved price, recipient, channel, dates and conditions.</label>
   <button className="rounded border px-3 py-2 disabled:opacity-50" type="button" disabled={!canDecide||!confirmed||snapshot.approved} onClick={()=>void submit('approve')}>Approve saved terms</button>
   <button className="rounded border px-3 py-2 disabled:opacity-50" type="button" disabled={busy||!!pending||!snapshot.approval||!!error} onClick={()=>void submit('revoke')}>Revoke approval</button>
   <OfferHistory key={`${lead}:${snapshot.version}`} lead={lead}/>
  </>}
 </section>;
}
