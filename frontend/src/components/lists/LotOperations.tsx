import {useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {z} from 'zod';
import {apiFetch} from '@/lib/api';
import {supabase} from '@/lib/supabase';
import {useProfile} from '@/hooks/useProfile';
import {useLotAction} from '@/hooks/useLotAction';
import {Button} from '@/components/ui/button';
import {Input} from '@/components/ui/input';
const candidateSchema=z.object({id:z.string().uuid(),lead_id:z.string().uuid(),address_std:z.string().nullable(),city:z.string().nullable(),county:z.string(),parcel_id:z.string().nullable(),is_vacant_lot:z.boolean().nullable(),input_hash:z.string().nullable(),blocked:z.string().nullable(),evaluation_id:z.string().uuid().nullable(),route:z.string().nullable(),score_current:z.boolean()});
const listSchema=z.object({count:z.number().int().nonnegative(),candidates:z.array(candidateSchema).max(50)});
type Candidate=z.infer<typeof candidateSchema>;
type Workflow=ReturnType<typeof useLotAction>;
export function LotOperations(){
 const {profile,isAdmin}=useProfile();
 return profile&&isAdmin?<Controls key={profile.id} actor={profile.id}/>:null;
}
function Controls({actor}:{actor:string}){
 const [offset,setOffset]=useState(0),[assignee,setAssignee]=useState(actor);
 const workflow=useLotAction(actor);
 const query=useQuery({queryKey:['lot-candidates',actor,offset],queryFn:async()=>listSchema.parse(await(await apiFetch(`/api/operations/lists/lots?offset=${offset}`)).json())});
 const team=useQuery({queryKey:['lot-assignees',actor],queryFn:async()=>{
  const {data,error}=await supabase.from('profiles').select('id,full_name,email').eq('status','approved').order('full_name').limit(100);
  if(error)throw error;
  return z.array(z.object({id:z.string().uuid(),full_name:z.string().nullable(),email:z.string()})).parse(data);
 }});
 return <section aria-label="Lot review and handoff" className="rounded-xl border bg-white p-4 space-y-3">
  <h2 className="text-xl font-semibold">Lot review and underwriting handoff</h2>
  <p>Review official parcel evidence before classifying a lot. A changed classification may require scoring again. Handoff creates a land record and assigned task; it does not complete underwriting or approve an offer.</p>
  <Button disabled={workflow.busy||query.isFetching} onClick={()=>void query.refetch()}>Refresh lot candidates</Button>
  {query.isLoading&&<p>Loading lot candidates…</p>}{query.error&&<p role="alert">Lot candidates unavailable: {query.error.message}</p>}
  {team.error&&<p role="alert">Team list unavailable. You can assign the handoff to yourself.</p>}
  <label className="block">Underwriting assignee<select aria-label="Underwriting assignee" className="block rounded border p-2" disabled={workflow.locked} value={assignee} onChange={e=>setAssignee(e.target.value)}>
   <option value={actor}>Assign to me</option>{team.data?.filter(p=>p.id!==actor).map(p=><option key={p.id} value={p.id}>{p.full_name??p.email}</option>)}
  </select></label>
  {workflow.error&&<p role="alert">{workflow.error}</p>}{workflow.notice&&<p role="status">{workflow.notice}</p>}
  {workflow.pending&&<div role="alert"><p>Unconfirmed lot {workflow.pending.kind}. The original request is retained.</p><Button disabled={workflow.busy} onClick={()=>workflow.pending&&void workflow.run(workflow.pending)}>Retry saved lot action</Button></div>}
  {query.data&&!query.error&&<>
   <p>{query.data.count} verified property associations</p>
   {query.data.candidates.map(item=><CandidateControl key={`${item.lead_id}:${item.input_hash}`} item={item} assignee={assignee} workflow={workflow}/>)}
   <div className="flex gap-2"><Button disabled={workflow.busy||offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous 50 lot candidates</Button><Button disabled={workflow.busy||offset+50>=query.data.count} onClick={()=>setOffset(offset+50)}>Next 50 lot candidates</Button></div>
  </>}
  <a className="underline" href="/land">Open land underwriting inbox</a>
 </section>;
}
function CandidateControl({item,assignee,workflow}:{item:Candidate;assignee:string;workflow:Workflow}){
 const [classification,setClassification]=useState(''),[evidence,setEvidence]=useState(''),[notes,setNotes]=useState(''),[confirmed,setConfirmed]=useState(false);
 const disabled=workflow.locked||!item.input_hash||!!item.blocked;
 const validUrl=z.string().url().safeParse(evidence).success&&evidence.startsWith('https://');
 return <article className="rounded border p-3 space-y-2">
  <h3 className="font-semibold">{item.address_std??'Address requires review'} · {item.city??'City unknown'}, {item.county}</h3>
  <p>Parcel: {item.parcel_id??'unknown'} · Recorded lot classification: {item.is_vacant_lot===null?'unknown':item.is_vacant_lot?'vacant lot':'not a vacant lot'}</p>
  {item.blocked&&<p>Review blocked: {item.blocked.replaceAll('_',' ')}</p>}
  <label className="block">Reviewed classification<select aria-label={`Reviewed classification for ${item.address_std??'property'}`} disabled={disabled} value={classification} onChange={e=>{setClassification(e.target.value);setConfirmed(false);}} className="block rounded border p-2">
   <option value="">Choose after reviewing evidence</option><option value="lot">Verified vacant lot</option><option value="not_lot">Verified not a vacant lot</option>
  </select></label>
  <Input label="Official lot evidence URL" disabled={disabled} value={evidence} maxLength={2000} onChange={e=>{setEvidence(e.target.value);setConfirmed(false);}}/>
  <Input label="Lot review notes" disabled={disabled} value={notes} maxLength={2000} onChange={e=>{setNotes(e.target.value);setConfirmed(false);}}/>
  <label className="block"><input type="checkbox" disabled={disabled} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/> I reviewed official evidence for this exact property and classification.</label>
  <Button disabled={disabled||!classification||!validUrl||!notes.trim()||!confirmed} onClick={()=>void workflow.run({kind:'review',body:{request_id:crypto.randomUUID(),lead_id:item.lead_id,input_hash:item.input_hash!,is_vacant_lot:classification==='lot',evidence_url:evidence,notes:notes.trim()}})}>Save lot classification</Button>
  <p>{item.score_current?`Current scoring route: ${item.route?.replaceAll('_',' ')??'unavailable'}`:'A current score is required before routing.'}</p>
  <Button disabled={disabled||!item.score_current||item.route!=='underwrite_lot'||!item.evaluation_id||item.is_vacant_lot!==true} onClick={()=>void workflow.run({kind:'handoff',lead_id:item.lead_id,body:{request_id:crypto.randomUUID(),evaluation_id:item.evaluation_id!,assigned_to:assignee}})}>Send to underwriting inbox</Button>
 </article>;
}
