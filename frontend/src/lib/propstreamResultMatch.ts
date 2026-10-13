import Papa from 'papaparse';
export type CsvRow=Record<string,string>;
export type ResultColumns={owner:string;address:string;city:string;state:string;zip:string;phone:string;email:string;phone2?:string;phone3?:string;phone4?:string;phone5?:string;email2?:string;email3?:string;email4?:string;email5?:string;dnc:string};
export function readResultCsv(text:string):{rows:CsvRow[];columns:string[]}{
 const result=Papa.parse<CsvRow>(text,{header:true,skipEmptyLines:'greedy'});
 const columns=result.meta.fields||[];
 if(result.errors.length||!columns.length||new Set(columns).size!==columns.length||Object.keys(result.meta.renamedHeaders||{}).length)throw new Error('Invalid or duplicate CSV columns.');
 if(!result.data.length||result.data.length>10000)throw new Error('Use 1–10,000 provider rows.');
 return {rows:result.data,columns};
}
const normalized=(s:string)=>s.normalize('NFKC').trim().toUpperCase().replace(/[.,]/g,'').replace(/\s+/g,' ');
const identity=(owner:string,address:string,city:string,state:string,zip:string)=>[owner,address,city,state,zip].every(x=>x?.trim())?JSON.stringify([owner,address,city,state,zip].map(normalized)):null;
const phone=(s:string)=>{const d=s.replace(/[\s()+.-]/g,'');const n=d.length===10?'1'+d:d;return /^1[2-9]\d{9}$/.test(n)?'+'+n:null;};
export function matchPropstreamResults(manifest:CsvRow[],provider:CsvRow[],columns:ResultColumns){
 if(!manifest.length||manifest.length>500)throw new Error('Use the current reconciliation sheet with 1–500 leads.');
 if(!columns.owner||!columns.address||!columns.city||!columns.state||!columns.zip||(!columns.phone&&!columns.email))throw new Error('Map owner, full property address, city, state, ZIP and at least one contact column.');
 const requests=new Set<string>(),leads=new Set<string>(),groups=new Map<string,CsvRow[]>();
 for(const row of manifest){
  if(row.action!=='reconcile'||!row.request_id||!row.lead_id||!/^[a-f0-9]{64}$/.test(row.input_hash))throw new Error('Use an unedited reconciliation sheet exported from WholesaleOS.');
  if(requests.has(row.request_id)||leads.has(row.lead_id))throw new Error('Duplicate request or lead in reconciliation sheet.');
  requests.add(row.request_id);leads.add(row.lead_id);
  const key=identity(row.owner_name,row.property_address,row.city,row.state,row.zip_code);
  if(key)groups.set(key,[...(groups.get(key)||[]),row]);
 }
 const found=new Map<string,{name:string;phone:string;email:string}[]>(),blocked=new Map<string,string>();
 const exceptions:{row:number;reason:string}[]=[];
 provider.forEach((row,index)=>{
  const key=identity(row[columns.owner],row[columns.address],row[columns.city],row[columns.state],row[columns.zip]);
  const candidates=key?groups.get(key):undefined;
  if(!candidates||candidates.length!==1){exceptions.push({row:index+2,reason:candidates?'Ambiguous owner/property identity':'No exact owner/property match'});if(candidates)for(const c of candidates)blocked.set(c.request_id,'Ambiguous owner/property identity');return;}
  const candidate=candidates[0];
  // Keep every flagged or unrecognized suppression value out of automatic mapping.
  // Scan DNC-labelled columns even if the operator leaves the mapping blank.
  const flags=Array.from(new Set([columns.dnc,...Object.keys(row).filter(k=>/dnc|do.?not.?call|suppression/i.test(k))])).filter(Boolean);
  if(flags.some(k=>row[k]?.trim()&&!['no','false','0','clear','not listed'].includes(row[k].trim().toLowerCase()))){blocked.set(candidate.request_id,'Provider suppression flag requires review');exceptions.push({row:index+2,reason:'Provider suppression flag requires review'});return;}
  const mappedContacts=new Set(Object.entries(columns).filter(([k])=>/^phone|^email/.test(k)).map(([,v])=>v).filter(Boolean));
  if(Object.keys(row).some(k=>/^(?:phone|mobile|landline|email|e-mail)(?:[ _-]?(?:number|address|[1-9]))?$/i.test(k)&&row[k]?.trim()&&!mappedContacts.has(k))){
   blocked.set(candidate.request_id,'Unmapped contact column; map all returned contacts');exceptions.push({row:index+2,reason:'Unmapped contact column'});return;
  }
  const contacts=[...(found.get(candidate.request_id)||[])];let hasContact=false;
  for(let slot=1;slot<=5;slot++){
   const phoneColumn=columns[(slot===1?'phone':'phone'+slot) as keyof ResultColumns];
   const emailColumn=columns[(slot===1?'email':'email'+slot) as keyof ResultColumns];
   const rawPhone=phoneColumn?row[phoneColumn]?.trim()||'':'';const rawEmail=emailColumn?row[emailColumn]?.trim()||'':'';
   if(!rawPhone&&!rawEmail)continue;hasContact=true;
   const mobile=rawPhone?phone(rawPhone):'';
   if((rawPhone&&!mobile)||(rawEmail&&!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(rawEmail))){
    blocked.set(candidate.request_id,'Invalid contact; review original result');exceptions.push({row:index+2,reason:'Invalid contact'});return;
   }
   const contact={name:row[columns.owner],phone:mobile||'',email:rawEmail};
   if(!contacts.some(x=>x.phone===contact.phone&&x.email.toLowerCase()===contact.email.toLowerCase()))contacts.push(contact);
  }
  if(!hasContact){blocked.set(candidate.request_id,'Missing contact; review original result');exceptions.push({row:index+2,reason:'Missing contact'});return;}
  found.set(candidate.request_id,contacts);
 });
 const matched:CsvRow[]=[],held:{request_id:string;lead_id:string;property_address:string;reason:string}[]=[];
 for(const row of manifest){
  const contacts=found.get(row.request_id)||[];const reason=blocked.get(row.request_id)||(contacts.length>5?'More than five contacts; review full provider result':contacts.length===0?'No matched provider row; do not infer no-match outcome':'');
  if(reason){held.push({request_id:row.request_id,lead_id:row.lead_id,property_address:row.property_address,reason});continue;}
  const result={...row,confirmed_match:'false',no_match:'false',actual_cents:'',provider_receipt:''};
  for(let n=1;n<=5;n++){const c=contacts[n-1];Object.assign(result,{['name_'+n]:c?.name||'',['phone_'+n]:c?.phone||'',['email_'+n]:c?.email||'',['phone_type_'+n]:'unknown'});}
  matched.push(result);
 }
 return {matched,held,exceptions};
}
