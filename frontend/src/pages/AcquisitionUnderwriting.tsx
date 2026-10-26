import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiFetch, ApiError } from '@/lib/api';
import { ScenarioSummary } from '@/components/acquisition/ScenarioSummary';
import { buildInputs, caseNames, emptyDraft, emptyEntry, fieldLabel, fieldUnit, inputPaths, strategyNames } from '@/lib/acquisitionInputs';
import type { Draft, Entry, Strategy } from '@/lib/acquisitionInputs';

import { loadQualification } from '@/lib/intakeQualification';

type Lead = { lead_id:string; property_id:string|null; property_address:string; city:string };
export type Analysis = { id:string; acquisition_revision:number; acquisition_status:string; acquisition_strategy:string; acquisition_inputs?:unknown; acquisition_outputs: { cases?:Record<string,{proposed_offer_range?:{low:string;high:string}|null;missing_inputs?:string[]}> } | null };
const button = 'border rounded-lg px-3 py-2 text-sm disabled:opacity-40';
const input = 'border border-gray-300 rounded p-2 w-full bg-white';
const errors = (error:unknown) => error instanceof Error ? error.message : 'Request unavailable';
const definite = (error:unknown) => error instanceof ApiError && [400,401,403,404,409,422].includes(error.status);
async function get<T>(url:string,signal?:AbortSignal):Promise<T> { return (await apiFetch(url,{signal})).json(); }
async function post<T>(url:string,body:unknown):Promise<T> { return (await apiFetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})).json(); }

export function AcquisitionUnderwriting({userId,workspace,onProposed}:{userId:string;workspace:string;onProposed:()=>void}) {
  const [after,setAfter]=useState<string|null>(null); const [lead,setLead]=useState<Lead|null>(null);
  const base=`/api/acquisition/workspaces/${workspace}`;
  const leads=useQuery({queryKey:['acquisition-entry',userId,workspace,after],queryFn:({signal})=>get<Lead[]>(`${base}/leads?limit=20${after?`&after=${after}`:''}`,signal),retry:false,gcTime:0,staleTime:0});
  return <details className="border rounded-xl p-4 bg-white"><summary className="font-semibold cursor-pointer">Underwrite a property and propose an offer</summary>
    <p className="text-sm text-gray-600 my-3">Choose a bound property. Each saved scenario keeps its own inputs and source evidence.</p>
    {leads.isPending?<p role="status">Loading properties…</p>:leads.isError?<p role="alert">{errors(leads.error)}</p>:<>
      <label>Property<select className={input} value={lead?.lead_id??''} onChange={e=>setLead(leads.data?.find(l=>l.lead_id===e.target.value)??null)}><option value="">Choose a property</option>{leads.data?.map(l=><option key={l.lead_id} value={l.lead_id}>{l.property_address}, {l.city}{!l.property_id?' — property binding incomplete':''}</option>)}</select></label>
      <div className="flex gap-2 mt-2"><button className={button} disabled={!after||leads.isFetching} onClick={()=>{setLead(null);setAfter(null);}}>First property page</button><button className={button} disabled={leads.data?.length!==20||leads.isFetching} onClick={()=>{setLead(null);setAfter(leads.data![19].lead_id);}}>More properties</button></div>
    </>}
    {lead && <PropertyWorkspace key={lead.lead_id} base={base} lead={lead} userId={userId} onProposed={onProposed}/>}
  </details>;
}

function PropertyWorkspace({base,lead,userId,onProposed}:{base:string;lead:Lead;userId:string;onProposed:()=>void}) {
  const [revisionAfter,setRevisionAfter]=useState(0); const [selected,setSelected]=useState<Analysis|null>(null);
  const path=`${base}/leads/${lead.lead_id}/underwriting`;
  const history=useQuery({queryKey:['acquisition-scenarios',userId,base,lead.lead_id,revisionAfter],queryFn:({signal})=>get<Analysis[]>(`${path}/scenarios?after=${revisionAfter}&limit=20`,signal),retry:false,gcTime:0,staleTime:0});
  return <section className="mt-4 space-y-4"><h3 className="font-semibold">{lead.property_address}</h3>
    {!lead.property_id && <p role="alert">This lead needs a canonical property binding before an offer can be proposed.</p>}
    <ScenarioEditor path={path} onSaved={analysis=>{setSelected(analysis);void history.refetch();}}/>
    <h4 className="font-semibold">Saved scenarios</h4>
    <button className={button} disabled={history.isFetching} onClick={()=>{setSelected(null);void history.refetch();}}>Refresh saved scenarios</button>
    {history.isFetching?<p role="status">Loading saved scenarios…</p>:history.isError?<p role="alert">{errors(history.error)}</p>:<div className="flex flex-wrap gap-2">{history.data?.map(a=><button className={button} key={a.id} onClick={()=>setSelected(a)}>Revision {a.acquisition_revision} · {a.acquisition_strategy.replaceAll('_',' ')} · {a.acquisition_status}</button>)}</div>}
    <div className="flex gap-2"><button className={button} disabled={!revisionAfter||history.isFetching} onClick={()=>{setSelected(null);setRevisionAfter(0);}}>First revision page</button><button className={button} disabled={history.data?.length!==20||history.isFetching||history.isError} onClick={()=>{setSelected(null);setRevisionAfter(history.data![19].acquisition_revision);}}>More revisions</button></div>
    {selected && !history.isError && <ProposalEditor key={selected.id} path={path} onRecalculated={()=>{void history.refetch();setSelected(null);}} base={base} analysis={selected} bound={!!lead.property_id} onProposed={onProposed}/>}
  </section>;
}

export function ScenarioEditor({path,onSaved,intake,disabled=false,onPending}:{path:string;onSaved:(analysis:Analysis,current?:boolean)=>void;
  intake?:{path:string;id:string;evidenceHash:string};disabled?:boolean;onPending?:(value:boolean)=>void}) {
  const [strategy,setStrategy]=useState<Strategy>('fix_and_flip'); const [buyer,setBuyer]=useState<Exclude<Strategy,'wholesale'>>('fix_and_flip');
  const [draft,setDraft]=useState<Draft>(emptyDraft); const [uncertainties,setUncertainties]=useState(['title','liens','occupancy','valuation','repairs','ownership','zoning','financing']);
  const [request,setRequest]=useState<{id:string;inputs:ReturnType<typeof buildInputs>;evidence_hash?:string}|null>(null);
  const [saved,setSaved]=useState(false); const [busy,setBusy]=useState(false); const lock=useRef(false); const [feedback,setFeedback]=useState('');
  const [preview,setPreview]=useState<Record<string,unknown>|null>(null);
  const populated=Object.values(draft).some(c=>Object.values(c).some(e=>e.value||e.source));
  const locked=disabled||busy||!!request||saved;
  useEffect(()=>{onPending?.(busy||!!request);},[busy,request,onPending]);
  function update(name:typeof caseNames[number],key:string,patch:Partial<Entry>) { setDraft(d=>({...d,[name]:{...d[name],[key]:{...(d[name][key]??emptyEntry()),...patch}}}));setPreview(null); }
  async function run(save:boolean) {
    if(lock.current||disabled)return;lock.current=true;setBusy(true);setFeedback('');
    let attempt=request;
    try {
      const inputs=attempt?.inputs??buildInputs(strategy,buyer,draft,uncertainties);
      if(!save) {setPreview(await post(`${path}/preview`,inputs));setFeedback('Preview calculated. It has not been saved.');return;}
      if(!attempt){
        let evidence_hash:string|undefined;
        if(intake){const fresh=await loadQualification(`${intake.path}/qualification-state`);
          if(fresh.evidence_hash!==intake.evidenceHash||fresh.assessment.classification!=='qualified'||!fresh.assessment.identity_link_current)
            throw new Error('Qualification changed. Close this draft and refresh the intake before starting another scenario.');
          evidence_hash=fresh.evidence_hash;
        }
        attempt={id:crypto.randomUUID(),inputs,...(evidence_hash?{evidence_hash}:{})};setRequest(attempt);
      }
      const response=await post<{analysis:Analysis;calculation:{status:string};binding_offer?:boolean;intake_context?:{analysis_id:string;has_intake:boolean;intake_id:string;assessment_id:string;qualification_current:boolean}}>(`${intake?`${intake.path}/underwriting`:path}/scenarios`,attempt);
      if(response.analysis?.id!==attempt.id)throw new Error('Save result is unconfirmed');
      if(intake && (response.binding_offer!==false||response.intake_context?.analysis_id!==attempt.id||response.intake_context?.intake_id!==intake.id
        ||response.intake_context?.assessment_id!==attempt.id||response.intake_context?.has_intake!==true||typeof response.intake_context?.qualification_current!=='boolean'))throw new Error('Intake provenance result is unconfirmed');
      onSaved(response.analysis,response.intake_context?.qualification_current);
      if(response.analysis.acquisition_status==='pending')setFeedback('Inputs saved; calculation is pending. Retry this same scenario when the calculator is available.');
      else {setRequest(null);setSaved(true);setFeedback(`Saved revision ${response.analysis.acquisition_revision}: ${response.analysis.acquisition_status}. ${intake?'Review the saved scenario details below.':'Select it below to review or propose an amount.'}`);}
    } catch(error) {if(definite(error))setRequest(null);setFeedback(attempt&&!definite(error)?'Save outcome unconfirmed. Retry the same scenario reference.':errors(error));}
    finally{setBusy(false);lock.current=false;}
  }
  return <details className="border rounded-lg p-3"><summary className="font-medium cursor-pointer">New underwriting scenario</summary>
    <p className="text-sm my-3">Blank means missing. Enter an explicit, sourced zero where appropriate. Rates are fractions: 0.08 means 8%. Holding costs exclude interest; closing costs exclude financing fees. Recheck fixed debt assumptions when the price changes.</p>
    <fieldset disabled={locked} className="space-y-3"><label>Strategy<select className={input} disabled={populated} value={strategy} onChange={e=>{setStrategy(e.target.value as Strategy);setPreview(null);}}>{Object.entries(strategyNames).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
      {strategy==='wholesale'&&<label>End buyer strategy<select className={input} disabled={populated} value={buyer} onChange={e=>{setBuyer(e.target.value as typeof buyer);setPreview(null);}}>{Object.entries(strategyNames).filter(([key])=>key!=='wholesale').map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>}
      {caseNames.map(name=><details key={name}><summary className="capitalize font-medium cursor-pointer">{name} case</summary><div className="space-y-4 mt-2">{inputPaths(strategy,buyer).map(key=>{const entry=draft[name][key]??emptyEntry();const unit=fieldUnit(key);const label=`${name}: ${fieldLabel(key)}`;return <fieldset key={key} className="border rounded p-3 grid gap-2 md:grid-cols-2"><legend>{fieldLabel(key)} ({unit})</legend>
        <label>Value<input aria-label={`${label} value`} className={input} inputMode="decimal" value={entry.value} onChange={e=>update(name,key,{value:e.target.value})}/></label>
        {unit!=='integer months'&&<><label>Source<input aria-label={`${label} source`} className={input} maxLength={500} value={entry.source} onChange={e=>update(name,key,{source:e.target.value})}/></label>
        <label>Evidence basis<select aria-label={`${label} basis`} className={input} value={entry.basis} onChange={e=>update(name,key,{basis:e.target.value as Entry['basis']})}><option value="estimate">Estimate</option><option value="source_reported">Source reported, unverified</option></select></label>
        <label>Confidence<select aria-label={`${label} confidence`} className={input} value={entry.confidence} onChange={e=>update(name,key,{confidence:e.target.value as Entry['confidence']})}>{['low','medium','high'].map(c=><option key={c}>{c}</option>)}</select></label>
        <label>Source date<input aria-label={`${label} date`} className={input} type="date" value={entry.as_of} onChange={e=>update(name,key,{as_of:e.target.value})}/></label></>}
      </fieldset>;})}</div></details>)}
      <fieldset><legend>Unresolved diligence</legend><div className="flex flex-wrap gap-3">{['title','liens','occupancy','valuation','repairs','ownership','zoning','financing'].map(key=><label key={key}><input type="checkbox" checked={uncertainties.includes(key)} onChange={e=>{setUncertainties(v=>e.target.checked?[...v,key]:v.filter(k=>k!==key));setPreview(null);}}/> {key}</label>)}</div></fieldset>
    </fieldset>
    <div className="flex flex-wrap gap-2 mt-4"><button className={button} disabled={locked} onClick={()=>void run(false)}>Calculate preview</button><button className={button} disabled={disabled||busy||saved} onClick={()=>void run(true)}>{request?'Retry same scenario':'Save scenario'}</button>
      <button className={button} disabled={disabled||busy||!!request} onClick={()=>{setDraft(emptyDraft());setSaved(false);setPreview(null);setFeedback('');}}>Discard draft / start new scenario</button></div>
    {feedback&&<p role="status" className="my-2">{feedback}</p>}
    {preview&&<ScenarioSummary output={preview}/>}
    {preview&&<details><summary>Preview results and missing inputs</summary><pre className="whitespace-pre-wrap break-words text-xs max-h-96 overflow-auto">{JSON.stringify(preview,null,2)}</pre></details>}
  </details>;
}

function ProposalEditor({base,path,onRecalculated,analysis,bound,onProposed}:{base:string;path:string;onRecalculated:()=>void;analysis:Analysis;bound:boolean;onProposed:()=>void}) {
  const [caseName,setCaseName]=useState('base');const [amount,setAmount]=useState('');const [note,setNote]=useState('');const [busy,setBusy]=useState(false);const lock=useRef(false);
  const [request,setRequest]=useState<{id:string;analysis_id:string;case:string;amount:string;note:string}|null>(null);const [done,setDone]=useState(false);const [feedback,setFeedback]=useState('');
  const range=analysis.acquisition_outputs?.cases?.[caseName]?.proposed_offer_range;
  async function propose(){if(lock.current)return;lock.current=true;setBusy(true);let attempt=request;
    try {if(!attempt){if(!/^\d+(\.\d{1,2})?$/.test(amount)||Number(amount)<=0||!note.trim())throw new Error('Enter a positive dollar amount and proposal rationale.');attempt={id:crypto.randomUUID(),analysis_id:analysis.id,case:caseName,amount,note:note.trim()};setRequest(attempt);}
      const result=await post<{id:string}>(`${base}/offers`,attempt);if(result.id!==attempt.id)throw new Error('Proposal result unconfirmed');setRequest(null);setDone(true);setFeedback('Proposal saved for review. No offer was sent.');onProposed();
    }catch(error){if(definite(error))setRequest(null);setFeedback(attempt&&!definite(error)?'Proposal outcome unconfirmed. Retry the same proposal reference.':errors(error));}finally{lock.current=false;setBusy(false);}}
  async function resume(){if(lock.current)return;lock.current=true;setBusy(true);
    try{const response=await post<{analysis:Analysis}>(`${path}/scenarios`,{id:analysis.id,inputs:analysis.acquisition_inputs});
      if(response.analysis?.id!==analysis.id)throw new Error('Calculation result unconfirmed');
      if(response.analysis.acquisition_status==='pending')setFeedback('Calculation remains pending. This request has not created another revision.');
      else onRecalculated();
    }catch(error){setFeedback(errors(error));}finally{lock.current=false;setBusy(false);}}
  return <section className="border rounded p-3 space-y-3"><h4 className="font-semibold">Propose from revision {analysis.acquisition_revision}</h4><p>Status: {analysis.acquisition_status}. The server checks that this remains the latest calculated revision.</p>
    {analysis.acquisition_outputs && <ScenarioSummary output={analysis.acquisition_outputs}/>}
    {analysis.acquisition_status==='pending' && analysis.acquisition_inputs != null && <button className={button} disabled={busy} onClick={()=>void resume()}>Resume saved calculation</button>}
    <fieldset disabled={busy||!!request||done||!bound||analysis.acquisition_status!=='calculated'} className="space-y-3"><label>Offer case<select className={input} value={caseName} onChange={e=>setCaseName(e.target.value)}>{caseNames.map(name=><option key={name}>{name}</option>)}</select></label>
      <p>Calculated range: {range?`$${range.low} to $${range.high}`:'Unavailable'}</p><label>Proposed amount (USD)<input className={input} inputMode="decimal" value={amount} onChange={e=>setAmount(e.target.value)}/></label><label>Proposal rationale<textarea className={input} maxLength={4000} value={note} onChange={e=>setNote(e.target.value)}/></label></fieldset>
    <button className={button} disabled={busy||done||(!request&&(!bound||analysis.acquisition_status!=='calculated'||!range||!amount||!note.trim()))} onClick={()=>void propose()}>{request?'Retry same proposal':'Create proposal for review'}</button>
    {feedback&&<p role="status">{feedback}</p>}
  </section>;
}
