import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { apiFetch, ApiError } from '@/lib/api';
import { useProfile } from '@/hooks/useProfile';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
const positive = z.number().int().positive();
const threshold = z.number().int().min(0).max(100);
const operationSchema = z.discriminatedUnion('action', [
  z.object({event_id:z.string().uuid(),action:z.literal('threshold'),expected_version:positive,score_threshold:threshold}),
  z.object({event_id:z.string().uuid(),action:z.literal('complete_received'),job_id:z.string().uuid()}),
]);
type Operation = z.infer<typeof operationSchema>;
const snapshotSchema = z.object({
  settings:z.object({score_threshold:threshold,version:positive}),open_count:z.number().int().nonnegative(),
  jobs:z.array(z.object({id:z.string().uuid(),lead_id:z.string().uuid(),state:z.enum(['queued','submitted','received','review']),requested_model:z.string(),created_at:z.string(),incident:z.string().nullable(),task_id:z.string().uuid().nullable()})).max(50),
  recent_actions:z.array(z.object({id:z.string().uuid(),operator_id:z.string().uuid(),action:z.string(),created_at:z.string()})).max(20),
});
const receiptSchema = z.object({event:z.object({id:z.string().uuid(),operator_id:z.string().uuid(),action:z.string(),payload:z.record(z.string(),z.unknown()),result:z.record(z.string(),z.unknown())})});
export function ScoringOperations(){
  const {profile,isAdmin}=useProfile();
  return profile&&isAdmin?<Controls key={profile.id} actor={profile.id}/>:null;
}
function Controls({actor}:{actor:string}){
  const queryClient=useQueryClient();
  const key=`hilltop.scoring-operation.v1.${actor}`;
  const [initial]=useState(()=>{try{const raw=sessionStorage.getItem(key);return {pending:raw?operationSchema.parse(JSON.parse(raw)):null,error:''};}catch{return {pending:null,error:'Saved scoring action is unreadable. Review recovery data before another action.'};}});
  const [pending,setPending]=useState<Operation|null>(initial.pending);
  const [busy,setBusy]=useState(false),[error,setError]=useState(initial.error),[notice,setNotice]=useState('');
  const [offset,setOffset]=useState(0),[draft,setDraft]=useState('');
  const [inspecting,setInspecting]=useState<string|null>(null);
  const query=useQuery({queryKey:['list-scoring',actor,offset],queryFn:async()=>snapshotSchema.parse(await(await apiFetch(`/api/operations/lists/scoring?offset=${offset}`)).json())});
  async function apply(operation:Operation){
    if(busy||initial.error)return;
    setBusy(true);setError('');setNotice('');
    const saved=pending??operation;
    try{
      sessionStorage.setItem(key,JSON.stringify(saved));setPending(saved);
      const {event}=receiptSchema.parse(await(await apiFetch('/api/operations/lists/scoring/actions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(saved)})).json());
      const payload:Record<string,unknown>=saved.action==='threshold'?{expected_version:saved.expected_version,score_threshold:saved.score_threshold}:{job_id:saved.job_id};
      if(event.id!==saved.event_id||event.operator_id!==actor||event.action!==saved.action||Object.keys(event.payload).length!==Object.keys(payload).length||Object.keys(payload).some(k=>event.payload[k]!==payload[k]))throw new Error('Scoring acknowledgement does not match the saved action.');
      const result=event.result;
      if(saved.action==='threshold'){
        if(result.score_threshold!==saved.score_threshold||result.version!==saved.expected_version+1)throw new Error('Threshold acknowledgement is unconfirmed.');
      }else if(result.job_id!==saved.job_id||!['completed','obsolete','review'].includes(String(result.state))||(result.state==='completed'&&result.evaluation_id!==saved.job_id))throw new Error('Scoring completion is unconfirmed.');
      sessionStorage.removeItem(key);setPending(null);setDraft('');
      setNotice(saved.action==='threshold'?`Threshold action saved. Audit ${event.id}.`:`Saved response processed: ${String(result.state)}. Audit ${event.id}.`);
      await query.refetch();
      await queryClient.invalidateQueries({queryKey:['list-scoring-evidence',actor]});
    }catch(e){
      if(e instanceof ApiError&&e.status===409){sessionStorage.removeItem(key);setPending(null);await query.refetch();}
      setError(e instanceof Error?e.message:'Scoring action is unconfirmed. Retry the saved reference.');
    }finally{setBusy(false);}
  }
  const data=query.data;
  const unavailable=busy||!!pending||!!initial.error||!!query.error;
  const validDraft=/^(0|[1-9][0-9]?|100)$/.test(draft);
  return <section aria-label="Scoring operations" className="rounded-xl border bg-white p-4 space-y-3">
    <h2 className="text-xl font-semibold">Scoring settings and recovery</h2>
    <p>The threshold suggests review or underwriting; it never grants permission to contact a seller. Changing it invalidates evaluations tied to the old settings and may require scoring again.</p>
    <Button disabled={busy||query.isFetching} onClick={()=>void query.refetch()}>Refresh scoring status</Button>
    {query.isLoading&&<p>Loading scoring status…</p>}
    {query.error&&<p role="alert">Scoring status unavailable: {query.error.message}</p>}
    {error&&<p role="alert">{error}</p>}
    {notice&&<p role="status">{notice}</p>}
    {pending&&<div role="alert"><p>Unconfirmed {pending.action==='threshold'?`threshold ${pending.score_threshold}`:`saved-response completion ${pending.job_id}`} · Audit {pending.event_id}</p><Button disabled={busy} onClick={()=>void apply(pending)}>Retry saved scoring action</Button></div>}
    {data&&<>
      <p>Current threshold: {data.settings.score_threshold}/100 · Settings version {data.settings.version}</p>
      <Input label="New scoring threshold" type="number" min="0" max="100" step="1" value={draft} disabled={unavailable} onChange={e=>setDraft(e.target.value)}/>
      <Button disabled={unavailable||!validDraft||Number(draft)===data.settings.score_threshold} onClick={()=>void apply({event_id:crypto.randomUUID(),action:'threshold',expected_version:data.settings.version,score_threshold:Number(draft)})}>Save scoring threshold</Button>
      <p>{data.open_count} unresolved scoring jobs</p>
      {data.jobs.map(job=><article className="rounded border p-3 space-y-2" key={job.id}>
        <p>{job.state} · {job.requested_model} · {job.created_at}</p>
        <p className="break-all">Job {job.id} · Lead {job.lead_id}</p>
        <Button onClick={()=>setInspecting(job.id)}>Inspect scoring evidence</Button>
        {job.incident&&<p>{job.incident.replaceAll('_',' ')} · Task {job.task_id??'awaiting owner assignment'}</p>}
        {job.state==='received'?<Button disabled={unavailable} onClick={()=>void apply({event_id:crypto.randomUUID(),action:'complete_received',job_id:job.id})}>Finish saved scoring response</Button>:<p>{job.state==='queued'?'Awaiting the scoring worker.':'Review saved job evidence before any new model request. Automatic resubmission is blocked.'}</p>}
      </article>)}
      <div className="flex gap-2"><Button disabled={busy||offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>Previous 50 scoring jobs</Button><Button disabled={busy||offset+50>=data.open_count} onClick={()=>setOffset(offset+50)}>Next 50 scoring jobs</Button></div>
      {inspecting&&<ScoringEvidence key={inspecting} actor={actor} jobId={inspecting} onClose={()=>setInspecting(null)}/>}
      <h3 className="font-semibold">Recent scoring actions</h3>
      {data.recent_actions.map(event=><p className="break-all" key={event.id}>{event.action} by {event.operator_id} at {event.created_at} · Audit {event.id}</p>)}
    </>}
  </section>;
}

const evidenceSchema=z.object({
  job:z.object({id:z.string().uuid(),lead_id:z.string().uuid(),state:z.enum(['queued','submitted','received','completed','review','obsolete']),
    requested_model:z.string(),model_version:z.string().nullable(),prompt_version:z.string(),model_receipt:z.string().nullable(),
    input_hash:z.string(),input_snapshot:z.record(z.string(),z.unknown()),assessment:z.record(z.string(),z.unknown()).nullable(),
    error_code:z.string().nullable(),created_at:z.string(),claimed_at:z.string().nullable(),received_at:z.string().nullable(),completed_at:z.string().nullable()}),
  freshness:z.object({current:z.boolean(),blocked:z.string().nullable(),input_hash:z.string().nullable(),changed_sections:z.array(z.string())}),
  evaluation:z.object({id:z.string().uuid(),score:z.number().int().min(0).max(100),route:z.string(),flags:z.array(z.string()),created_at:z.string()}).nullable(),
  outreach_authorized:z.literal(false),
});
function ScoringEvidence({actor,jobId,onClose}:{actor:string;jobId:string;onClose:()=>void}){
  const query=useQuery({queryKey:['list-scoring-evidence',actor,jobId],queryFn:async()=>{
    const value=evidenceSchema.parse(await(await apiFetch(`/api/operations/lists/scoring/jobs/${jobId}`)).json());
    if(value.job.id!==jobId)throw new Error('Scoring evidence belongs to another job.');
    return value;
  }});
  const data=query.error?undefined:query.data;
  return <section aria-label="Scoring evidence" className="rounded border p-4 space-y-3">
    <div className="flex flex-wrap gap-2"><h3 className="font-semibold">Scoring evidence</h3><Button onClick={onClose}>Close scoring evidence</Button><Button disabled={query.isFetching} onClick={()=>void query.refetch()}>Refresh scoring evidence</Button></div>
    {query.isLoading&&<p>Loading scoring evidence…</p>}
    {query.error&&<p role="alert">Evidence unavailable: {query.error.message}</p>}
    {data&&<>
      <p className="break-all">Job {data.job.id} · Lead {data.job.lead_id}</p>
      <p>State: {data.job.state}. {data.freshness.current?'Saved evidence matches current evidence.':'Saved evidence is no longer current.'}</p>
      {data.freshness.blocked&&<p>Current evidence unavailable: {data.freshness.blocked.replaceAll('_',' ')}</p>}
      {!!data.freshness.changed_sections.length&&<p>Changed: {data.freshness.changed_sections.map(s=>s.replaceAll('_',' ')).join(', ')}</p>}
      {data.job.error_code&&<p>Validation issue: {data.job.error_code.replaceAll('_',' ')}</p>}
      <p>Requested model: {data.job.requested_model} · Returned model: {data.job.model_version??'not recorded'}</p>
      <p className="break-all">Provider receipt: {data.job.model_receipt??'not recorded'}</p>
      <p>Created: {data.job.created_at} · Submitted: {data.job.claimed_at??'not submitted'} · Response saved: {data.job.received_at??'not received'} · Completed: {data.job.completed_at??'not completed'}</p>
      {data.job.state==='submitted'&&<p>Provider outcome is unconfirmed. Compare provider records with this job before reconciliation. This screen cannot submit another request.</p>}
      {data.job.state==='review'&&<p>The saved response failed validation. Review its evidence and validation issue; no score or outreach permission is implied.</p>}
      {data.evaluation&&<p>Saved score: {data.evaluation.score}/100 · Suggested route: {data.evaluation.route.replaceAll('_',' ')}. {data.evaluation.flags.map(s=>s.replaceAll('_',' ')).join('; ')}</p>}
      <details><summary>Evidence used for this scoring request</summary><pre className="whitespace-pre-wrap break-all text-sm">{JSON.stringify(data.job.input_snapshot,null,2)}</pre></details>
      {data.job.assessment?<details><summary>Saved model response — untrusted content</summary><pre className="whitespace-pre-wrap break-all text-sm">{JSON.stringify(data.job.assessment,null,2)}</pre></details>:<p>No model response is stored.</p>}
      <p>Inspection does not alter the job, call the model, or authorize seller contact.</p>
    </>}
  </section>;
}
