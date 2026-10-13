import {useRef,useState} from 'react';
import {useQuery,useQueryClient} from '@tanstack/react-query';
import {apiFetch,ApiError} from '@/lib/api';
import {valuationEventSchema,valuationInputSchema,valuationRequestSchema,valuationSnapshotSchema} from '@/lib/landValuation';
import {ZodError,type z} from 'zod';
export function useLandValuation(actor:string,landId:string){
 const key=`hilltop.land-valuation.v1.${actor}.${landId}`;
 const [initial]=useState(()=>{try{
  const value=sessionStorage.getItem(key);const pending=value?valuationRequestSchema.parse(JSON.parse(value)):null;
  if(pending&&pending.land_lead_id!==landId)throw new Error('Wrong land record');
  return {pending,error:''};
 }catch{return {pending:null,error:'Saved valuation request is unreadable. Inspect recovery data before another save.'};}});
 const [pending,setPending]=useState(initial.pending),[busy,setBusy]=useState(false),[error,setError]=useState(initial.error),[notice,setNotice]=useState('');
 const active=useRef(false),queries=useQueryClient();
 const query=useQuery({queryKey:['land-valuation',actor,landId],queryFn:async()=>{
  const parsed=valuationSnapshotSchema.safeParse(await(await apiFetch(`/api/land-underwriting/valuations/${landId}`)).json());
  if(!parsed.success)throw new Error('Saved valuation data could not be verified. Refresh before editing.');
  const snapshot=parsed.data;
  if(snapshot.land_lead_id!==landId||snapshot.comp&&snapshot.comp.land_lead_id!==landId)throw new Error('Saved valuation belongs to another land record');
  return snapshot;
 }});
 async function run(request:z.infer<typeof valuationRequestSchema>){
  if(active.current||initial.error)return;active.current=true;setBusy(true);setError('');setNotice('');
  try{
   const saved=valuationRequestSchema.parse(pending??request);
   sessionStorage.setItem(key,JSON.stringify(saved));setPending(saved);
   const value=await(await apiFetch(`/api/land-underwriting/valuations/${landId}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(saved.body)})).json();
   const event=valuationEventSchema.parse(value.event);
   if(value.outreach_authorized!==false||event.id!==saved.body.request_id||event.operator_id!==actor||event.land_lead_id!==landId||event.expected_hash!==saved.body.expected_hash||JSON.stringify(event.payload)!==JSON.stringify(saved.body.payload)||event.comp_id!==event.saved_snapshot.comp?.id||event.saved_snapshot.land_lead_id!==landId||event.saved_snapshot.comp.land_lead_id!==landId)throw new Error('Valuation receipt does not match the saved request');
   sessionStorage.removeItem(key);setPending(null);
   setNotice(`Valuation receipt confirmed, revision ${event.saved_snapshot.comp.revision}. Reloading current analysis; no offer price or lead stage was changed.`);
   await query.refetch();await queries.invalidateQueries({queryKey:['land_leads']});
  }catch(e){
   if(e instanceof ApiError&&e.status===409){sessionStorage.removeItem(key);setPending(null);await query.refetch();}
   setError(e instanceof ZodError?'Valuation receipt could not be verified. Retry the original saved request.':e instanceof Error?e.message:'Valuation save is unconfirmed. Retry its original request.');
  }finally{active.current=false;setBusy(false);}
 }
 async function save(expectedHash:string,input:unknown){
  try{const payload=valuationInputSchema.parse(input);await run({land_lead_id:landId,body:{request_id:crypto.randomUUID(),expected_hash:expectedHash,payload}});}
  catch(e){setError(e instanceof ZodError?e.issues.slice(0,3).map(issue=>{const labels:Record<string,string>={address:'Address',price:'Sale price',sqft:'Area',date:'Sale date',distance_mi:'Distance',source_url:'Source URL',avg_house_arv:'House ARV',house_comp_count:'House comp count',tav:'Tax assessed value',tav_assessment_date:'Assessment date',comp_notes:'Notes'};const field=labels[String(issue.path.at(-1))]??'';const row=issue.path[0]==='direct_comp_details'&&typeof issue.path[1]==='number'?`Comparable ${issue.path[1]+1} `:'';return `${row}${field}${row||field?': ':''}${issue.message}`;}).join('; '):e instanceof Error?e.message:'Invalid valuation inputs');}
 }
 return {query,pending,busy,error,notice,locked:busy||!!pending||!!initial.error,save,retry:()=>pending&&run(pending)};
}
