import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {apiFetch} from '@/lib/api';
import {inboxSchema} from '@/lib/lotWorkflow';
import {useProfile} from '@/hooks/useProfile';
import {useLotAction} from '@/hooks/useLotAction';
import {Button} from '@/components/ui/button';
type OpenLand=(id:string,leadId:string)=>Promise<void>;
export function LotInbox({onOpen}:{onOpen:OpenLand}){
 const {profile,isApproved}=useProfile();
 return profile&&isApproved?<Inbox key={profile.id} actor={profile.id} onOpen={onOpen}/>:null;
}
function Inbox({actor,onOpen}:{actor:string;onOpen:OpenLand}){
 const [offset,setOffset]=useState(0),[opening,setOpening]=useState(false),[openError,setOpenError]=useState('');
 const [opened,setOpened]=useState<Set<string>>(()=>new Set());
 const [confirmed,setConfirmed]=useState<Set<string>>(()=>new Set());
 const workflow=useLotAction(actor);
 const query=useQuery({queryKey:['lot-inbox',actor,offset],queryFn:async()=>inboxSchema.parse(await(await apiFetch(`/api/land-underwriting/handoffs?offset=${offset}`)).json())});
 async function open(id:string,landId:string,leadId:string){
  setOpening(true);setOpenError('');
  try{await onOpen(landId,leadId);setOpened(current=>new Set(current).add(id));}
  catch(e){setOpenError(e instanceof Error?e.message:'Land record could not be opened');}
  finally{setOpening(false);}
 }
 return <section aria-label="Lot underwriting inbox" className="rounded-xl border bg-white p-4 space-y-3">
  <h2 className="text-xl font-semibold">Lot underwriting inbox</h2>
  <p>Open the linked land record and review the supplied evidence before acknowledging receipt. Ownership, zoning, utilities, buildability and valuation still require underwriting.</p>
  <Button disabled={workflow.busy||query.isFetching} onClick={()=>void query.refetch()}>Refresh underwriting inbox</Button>
  {query.isLoading&&<p>Loading underwriting handoffs…</p>}{query.error&&<p role="alert">Underwriting inbox unavailable: {query.error.message}</p>}
  {openError&&<p role="alert">{openError}</p>}{workflow.error&&<p role="alert">{workflow.error}</p>}{workflow.notice&&<p role="status">{workflow.notice}</p>}
  {workflow.pending&&<div role="alert"><p>Unconfirmed lot {workflow.pending.kind}. Retry the original request.</p><Button disabled={workflow.busy} onClick={()=>workflow.pending&&void workflow.run(workflow.pending)}>Retry saved lot action</Button></div>}
  {query.data&&!query.error&&<>
   <p>{query.data.count} underwriting handoffs</p>
   {query.data.handoffs.map(row=><article key={row.id} className="rounded border p-3 space-y-2">
    <h3 className="font-semibold">{row.address_std??'Address unavailable'} · {row.county}</h3>
    <p>Score: {row.score}/100 · {row.current?'Scoring evidence is current.':'Scoring evidence has changed; review before relying on the score.'}</p>
    <a className="underline" href={row.evidence_url} target="_blank" rel="noreferrer">Reviewed lot source</a><p>{row.review_notes}</p>
    <details><summary>Scoring evidence and reasons</summary><pre className="whitespace-pre-wrap break-all text-sm">{JSON.stringify({input:row.scoring_input,reasons:row.reasons,flags:row.flags},null,2)}</pre></details>
    <p className="break-all">Task {row.task_id} · Handoff {row.id}</p>
    <Button disabled={opening} onClick={()=>void open(row.id,row.land_lead_id,row.lead_id)}>Open linked land record</Button>
    {row.acknowledged_at?<p>Receipt acknowledged by {row.acknowledged_by} at {row.acknowledged_at}. Underwriting task remains separate.</p>:<>
     <label className="block"><input type="checkbox" disabled={!opened.has(row.id)||workflow.locked} checked={confirmed.has(row.id)} onChange={e=>setConfirmed(current=>{const next=new Set(current);if(e.target.checked)next.add(row.id);else next.delete(row.id);return next;})}/> I opened the land record and reviewed this handoff; I am acknowledging receipt only.</label>
     <Button disabled={!opened.has(row.id)||!confirmed.has(row.id)||workflow.locked} onClick={()=>void workflow.run({kind:'acknowledge',id:row.id,lead_id:row.lead_id,land_lead_id:row.land_lead_id,task_id:row.task_id})}>Acknowledge underwriting receipt</Button>
    </>}
   </article>)}
   <div className="flex gap-2"><Button disabled={workflow.busy||offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous 50 handoffs</Button><Button disabled={workflow.busy||offset+50>=query.data.count} onClick={()=>setOffset(offset+50)}>Next 50 handoffs</Button></div>
  </>}
 </section>;
}
