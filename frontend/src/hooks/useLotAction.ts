import {useState} from 'react';
import {useQueryClient} from '@tanstack/react-query';
import {ApiError} from '@/lib/api';
import {lotActionSchema,writeLotAction,type LotAction} from '@/lib/lotWorkflow';
export function useLotAction(actor:string){
 const storageKey=`hilltop.lot-action.v1.${actor}`;
 const [initial]=useState(()=>{try{const raw=sessionStorage.getItem(storageKey);return {pending:raw?lotActionSchema.parse(JSON.parse(raw)):null,error:''};}catch{return {pending:null,error:'Saved lot action is unreadable. Inspect recovery data before another action.'};}});
 const [pending,setPending]=useState<LotAction|null>(initial.pending);
 const [busy,setBusy]=useState(false),[error,setError]=useState(initial.error),[notice,setNotice]=useState('');
 const queries=useQueryClient();
 async function run(action:LotAction){
  if(busy||initial.error)return;
  setBusy(true);setError('');setNotice('');
  try{
   const saved=lotActionSchema.parse(pending??action);
   sessionStorage.setItem(storageKey,JSON.stringify(saved));setPending(saved);
   const message=await writeLotAction(actor,saved);
   sessionStorage.removeItem(storageKey);setPending(null);setNotice(message);
   await Promise.all(['lot-candidates','lot-inbox','land_leads','list-scoring'].map(key=>queries.invalidateQueries({queryKey:[key]})));
  }catch(e){
   if(e instanceof ApiError&&e.status===409){sessionStorage.removeItem(storageKey);setPending(null);await Promise.all(['lot-candidates','lot-inbox'].map(key=>queries.invalidateQueries({queryKey:[key,actor]})));}
   setError(e instanceof Error?e.message:'Lot action is unconfirmed. Retry its saved reference.');
  }finally{setBusy(false);}
 }
 return {pending,busy,error,notice,run,locked:busy||!!pending||!!initial.error};
}
