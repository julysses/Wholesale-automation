import Papa from 'papaparse';
import {z} from 'zod';
const itemSchema=z.object({event_id:z.string().uuid(),request_id:z.string().uuid(),lead_id:z.string().uuid(),action:z.enum(['review_status','prepare','start','reconcile']),payload:z.record(z.string(),z.unknown())});
export const batchSchema=z.object({batch_id:z.string().uuid(),items:z.array(itemSchema).min(1).max(500)});
export type Batch=z.infer<typeof batchSchema>;export type Action=Batch['items'][number]['action'];
const integer=(value:string)=>{if(!/^\d+$/.test(value))throw new Error('Costs and balances must be whole cents.');return Number(value);};
export function parseBulkCsv(csv:string,action:Action):Batch{
 const parsed=Papa.parse<Record<string,string>>(csv,{header:true,skipEmptyLines:'greedy'});
 if(parsed.errors.length)throw new Error('CSV has invalid or duplicate columns. Correct it before importing.');
 if(parsed.data.length<1||parsed.data.length>500)throw new Error('Use 1–500 rows per batch.');
 const items=parsed.data.map((r,index)=>{
  const common={event_id:crypto.randomUUID(),request_id:r.request_id||crypto.randomUUID(),lead_id:r.lead_id,action};
  if(r.action!==action)throw new Error(`Row ${index+1}: select the matching batch step.`);
  const confirmed=(key:string)=>{if(r[key]!=='true')throw new Error(`Row ${index+1}: ${key} must be explicitly true.`);return true;};
  let payload:Record<string,unknown>;
  if(action==='review_status'){
   if(!['true','false'].includes(r.active))throw new Error(`Row ${index+1}: active must be true or false.`);
   payload={signal_id:r.signal_id,signal_hash:r.signal_hash,auction_date:r.auction_date,active:r.active==='true',status_evidence_url:r.status_evidence_url,notes:r.notes,confirmed_current_status:confirmed('confirmed_current_status')};
  }else if(action==='prepare')payload={signal_id:r.signal_id,signal_hash:r.signal_hash,input_hash:r.input_hash,quote_cents:integer(r.quote_cents),prepaid_balance_cents:integer(r.prepaid_balance_cents),quote_reference:r.quote_reference,owner_evidence_url:r.owner_evidence_url,status_evidence_url:r.status_evidence_url,notes:r.notes,all_pages_reviewed:confirmed('all_pages_reviewed')};
  else if(action==='start')payload={input_hash:r.input_hash};
  else{
   if(!r.request_id)throw new Error(`Row ${index+1}: original request ID required.`);
   const contacts=[];
   for(let n=1;n<=5;n++)if(r[`phone_${n}`]||r[`email_${n}`])contacts.push({name:r[`name_${n}`]||null,phone:r[`phone_${n}`]||null,email:r[`email_${n}`]||null,phone_type:r[`phone_type_${n}`]||'unknown'});
   if(!contacts.length&&r.no_match!=='true')throw new Error(`Row ${index+1}: supply matched contacts or explicitly mark no_match true.`);
   if(contacts.length&&r.no_match==='true')throw new Error(`Row ${index+1}: contacts conflict with no_match.`);
   payload={input_hash:r.input_hash,actual_cents:integer(r.actual_cents),provider_receipt:r.provider_receipt,contacts,confirmed_match:confirmed('confirmed_match')};
  }
  if(action==='start'&&!r.request_id)throw new Error(`Row ${index+1}: original request ID required.`);
  return {...common,payload};
 });
 if(new Set(items.map(x=>x.lead_id)).size!==items.length)throw new Error('Duplicate lead rows are not allowed.');
 return batchSchema.parse({batch_id:crypto.randomUUID(),items});
}

// Exact headers from PropStream's publicly linked Contacts import template.
// Preserve the verified full owner name; do not guess surname or mailing address.
export function propstreamContactRows(manifest:Record<string,unknown>[]){
 return manifest.map(r=>({'First Name':r.owner_name||'','Last Name':'','Email':'','Phone':'','Mobile Phone':'','Landline':'',
 'Street Address':r.property_address||'','City':r.city||'','State':r.state||'','Zip':r.zip_code||'',
 'Mail Street Address':'','Mail City':'','Mail State':'','Mail Zip':'','Mail Address Same':'','Type':'Owner','Status':'New'}));
}
