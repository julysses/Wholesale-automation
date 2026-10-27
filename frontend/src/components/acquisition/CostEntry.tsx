import { useEffect, useRef, useState } from 'react';
import { costMinorUnits, restoreCostImport, submitCostImport, validateNewCostRequest, type PendingCostImport } from '@/lib/costImport';
import { readCostCoverage, usdMinor } from '@/lib/costCoverage';
export type CostLink = { campaign: string; review: string; external: string; account: string };
const button = 'rounded border px-3 py-2 text-sm disabled:opacity-40';
const input = 'block w-full rounded border p-2';
const sameLink = (a: CostLink | null, b: CostLink | null) => !!a && !!b && a.campaign === b.campaign && a.review === b.review && a.external === b.external && a.account === b.account;
export function CostEntry({ userId, workspace, intake, link, allowed, locked, refreshLink, onPending }: {
  userId: string; workspace: string; intake: string; link: CostLink | null; allowed: boolean; locked: boolean;
  refreshLink: () => Promise<CostLink | null>; onPending: (pending: boolean) => void;
}) {
  const pointer = `cost-entry:v1:${userId}:${workspace}:${intake}`;
  const [initial] = useState(() => { try {
    const campaign = sessionStorage.getItem(pointer);
    return { pending: campaign ? restoreCostImport(sessionStorage,userId,workspace,campaign) : null, invalid:false };
  } catch { return { pending:null, invalid:true }; } });
  const [pending,setPending] = useState<PendingCostImport | null>(initial.pending);
  const [preview,setPreview] = useState<PendingCostImport | null>(null);
  const [open,setOpen] = useState(!!initial.pending || initial.invalid);
  const [date,setDate] = useState(''); const [amount,setAmount] = useState('');
  const [coverage,setCoverage] = useState<'complete'|'partial'|'withdrawn'>('partial');
  const [zone,setZone] = useState(''); const [observed,setObserved] = useState('');
  const [reference,setReference] = useState(''); const [hash,setHash] = useState(''); const [ack,setAck] = useState(false);
  const [busy,setBusy] = useState(false); const flight=useRef(false); const [feedback,setFeedback] = useState('');
  useEffect(()=>{onPending(!!pending || busy || initial.invalid);},[pending,busy,initial.invalid,onPending]);
  const available = allowed && !locked && !!link && !initial.invalid;
  const editable = available && !busy && !pending;
  function edit(change:()=>void) {change();setPreview(null);setAck(false);setFeedback('');}
  async function prepare() {
    if (!editable || flight.current || !link) return;
    flight.current=true;setBusy(true);setFeedback('');setPreview(null);setAck(false);
    try {
      const fresh=await refreshLink(); if (!sameLink(fresh,link)) throw new Error('Campaign review changed. Refresh before preparing evidence.');
      const report=await readCostCoverage(workspace,link.campaign,date,date);
      const existing=restoreCostImport(sessionStorage,userId,workspace,link.campaign);
      sessionStorage.setItem(pointer,link.campaign);
      if(existing) {setPending(existing);setFeedback('An earlier campaign cost request needs exact reconciliation.');return;}
      if (report.reporting_timezone && report.reporting_timezone !== zone) throw new Error('Use the established account reporting timezone: '+report.reporting_timezone);
      const request: PendingCostImport={user:userId,workspace,campaign:link.campaign,request:{id:crypto.randomUUID(),link_review_id:link.review,reviewed:true,data:{
        date,amount_minor:coverage==='withdrawn'?null:costMinorUnits(amount),coverage,currency:'USD',reporting_timezone:zone,observed_at:observed,
        external_campaign_id:link.external,ad_account_id:link.account,evidence_ref:reference.trim(),evidence_hash:hash,expected_revision:report.days[0]?.revision ?? 0,
      }}};
      validateNewCostRequest(request.request);setPreview(request);
    } catch(error) {setFeedback(error instanceof Error?error.message:'Unable to prepare reviewed cost.');}
    finally {flight.current=false;setBusy(false);}
  }
  async function save() {
    if(flight.current || locked || initial.invalid || (!pending && (!preview || !ack || !available))) return;
    const request=pending ?? preview!; const retrying=!!pending;
    flight.current=true;setBusy(true);setFeedback('');
    try {
      if(!retrying) {
        const fresh=await refreshLink();const d=request.request.data;
        if(!sameLink(fresh,{campaign:request.campaign,review:request.request.link_review_id,external:d.external_campaign_id,account:d.ad_account_id})) throw new Error('Campaign review changed. Prepare the evidence again.');
        const report=await readCostCoverage(workspace,request.campaign,d.date,d.date);
        if((report.days[0]?.revision ?? 0)!==d.expected_revision || (report.reporting_timezone && report.reporting_timezone!==d.reporting_timezone)) throw new Error('Daily evidence changed. Prepare the evidence again.');
      }
      sessionStorage.setItem(pointer,request.campaign);
      await submitCostImport(sessionStorage,request);
      setPending(null);setPreview(null);setAck(false);
      setFeedback('Cost evidence recorded. Reload campaign costs to see the latest coverage.');
    } catch(error) {
      try {setPending(restoreCostImport(sessionStorage,userId,workspace,request.campaign));} catch {setPending(request);}
      setPreview(null);setAck(false);
      setFeedback(`${error instanceof Error?error.message:'Cost result unconfirmed'}. Any retained request must be reconciled exactly before entering different evidence.`);
    } finally {flight.current=false;setBusy(false);}
  }
  const shown=pending ?? preview;
  return <section aria-label="Reviewed campaign cost entry" className="rounded border p-4 space-y-3">
    <button className={button} aria-expanded={open} onClick={()=>setOpen(v=>!v)}>{open?'Hide cost entry':'Enter reviewed campaign costs'}</button>
    {open && <><p className="text-sm">Record reviewed daily USD evidence or a correction. This does not retrieve Meta costs, change the campaign budget or authorize spending. Owner/admin access and MFA are required.</p>
      {initial.invalid && <p role="alert">Saved cost request cannot be read. Reconcile it before recording different evidence.</p>}
      {!link && !pending && <p>A current reviewed campaign link is required.</p>}
      <fieldset disabled={!editable} className="grid gap-3 sm:grid-cols-2">
        <label>Cost reporting date<input type="date" className={input} value={date} onChange={e=>edit(()=>setDate(e.target.value))}/></label>
        <label>Evidence coverage<select className={input} value={coverage} onChange={e=>edit(()=>setCoverage(e.target.value as typeof coverage))}><option value="partial">Partial day</option><option value="complete">Complete day</option><option value="withdrawn">Withdraw prior evidence</option></select></label>
        <label>Recorded cost (USD)<input className={input} inputMode="decimal" disabled={coverage==='withdrawn'} value={amount} onChange={e=>edit(()=>setAmount(e.target.value))}/></label>
        <label>Account reporting timezone<input className={input} placeholder="America/Chicago" value={zone} onChange={e=>edit(()=>setZone(e.target.value))}/></label>
        <label>Evidence observed at (with timezone)<input className={input} placeholder="2026-10-25T06:00:00Z" value={observed} onChange={e=>edit(()=>setObserved(e.target.value))}/></label>
        <label>Private cost evidence reference<input className={input} maxLength={1000} value={reference} onChange={e=>edit(()=>setReference(e.target.value))}/></label>
        <label>Evidence SHA-256<input className={input} maxLength={64} value={hash} onChange={e=>edit(()=>setHash(e.target.value))}/></label>
      </fieldset>
      <button className={button} disabled={!editable} onClick={()=>void prepare()}>Prepare cost revision</button>
      {shown && <div className="rounded border p-3 text-sm break-words"><h5 className="font-semibold">{pending?'Pending exact cost request':'Review proposed cost revision'}</h5><p>{shown.request.data.date} · {shown.request.data.coverage} · {usdMinor(shown.request.data.amount_minor===null?null:String(shown.request.data.amount_minor))}</p><p>Revision {shown.request.data.expected_revision+1} · {shown.request.data.reporting_timezone}</p><p>Observed: {shown.request.data.observed_at}</p><p>Campaign: {shown.campaign}</p><p>Account: {shown.request.data.ad_account_id} · External campaign: {shown.request.data.external_campaign_id}</p><p>Campaign review: {shown.request.link_review_id}</p><p>Evidence: {shown.request.data.evidence_ref}</p><p>SHA-256: {shown.request.data.evidence_hash}</p><p>Request: {shown.request.id}</p></div>}
      {preview && !pending && <label className="flex gap-2"><input type="checkbox" checked={ack} disabled={busy || !available} onChange={e=>setAck(e.target.checked)}/>I reviewed the source evidence, reporting day, amount and proposed revision.</label>}
      <button className={button} disabled={busy || locked || initial.invalid || (!pending && (!preview || !ack || !available))} onClick={()=>void save()}>{busy?'Checking cost evidence…':pending?'Retry exact cost request':'Record reviewed cost'}</button>
      {pending && <p className="text-sm">The earlier result is uncertain. Retry retains its original evidence, timestamp and revision, even if attribution has since changed.</p>}
      {feedback && <p role="status">{feedback}</p>}
    </>}
  </section>;
}
