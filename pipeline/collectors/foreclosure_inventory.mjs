// Convert reviewed browser index captures to bounded, review-only manifests.
// This never claims notice review, current distress, property identity or outreach permission.
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {randomUUID} from 'node:crypto';
import {canonicalJSON,sha256} from '../../frontend/supabase/functions/daily-list-ingest/core.mjs';
import {preflight} from './preflight.mjs';
const fail=message=>{throw new Error(message);};
const isoDate=value=>{
 if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value)||!Number.isFinite(Date.parse(value))||new Date(value).toISOString().slice(0,10)!==value)fail('Invalid date');
 return value;
};
const countySources={Dallas:'https://dallas.tx.publicsearch.us/',Collin:'https://apps2.collincountytx.gov/ForeclosureNotices/'};
const documentURL=(county,id)=>county==='Dallas'?`https://dallas.tx.publicsearch.us/doc/${id}`:`https://apps2.collincountytx.gov/ForeclosureNotices/DetailPage/${id}`;
const mmddyyyy=value=>{
 const m=typeof value==='string'&&value.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
 if(!m)fail('Unexpected county date layout');
 return isoDate(`${m[3]}-${m[1].padStart(2,'0')}-${m[2].padStart(2,'0')}`);
};
export function normalizeDallasCapture(capture){
 const u=new URL(capture.source);
 if(u.origin!=='https://dallas.tx.publicsearch.us'||u.pathname!=='/results'||u.searchParams.get('department')!=='FC'||u.searchParams.get('searchType')!=='advancedSearch')fail('Expected official Dallas foreclosure recorded-date search');
 if([...u.searchParams.keys()].some(k=>/sale/i.test(k)))fail('Clear sale-date filters');
 const range=u.searchParams.get('recordedDateRange')?.match(/^(\d{4})(\d{2})(\d{2}),(\d{4})(\d{2})(\d{2})$/);
 if(!range)fail('Recorded-date range required');
 const window_start=isoDate(`${range[1]}-${range[2]}-${range[3]}`),window_end=isoDate(`${range[4]}-${range[5]}-${range[6]}`);
 if(!Array.isArray(capture.passes)||capture.passes.length!==2)fail('Two captured passes required');
 let page_size;
 const scans=capture.passes.map(pass=>{
  if(!Array.isArray(pass)||!pass.length)fail('Missing pages');
  return pass.map((p,i)=>{
   const m=p.status?.match(/^(\d+)-(\d+) of (\d+) results for "(\d{2}\/\d{2}\/\d{4})-(\d{2}\/\d{2}\/\d{4})"$/);
   if(!m||!Array.isArray(p.rows)||mmddyyyy(m[4])!==window_start||mmddyyyy(m[5])!==window_end)fail('Range/filter evidence missing');
   if(page_size===undefined)page_size=Number(m[2]);
   if(Number(m[1])!==i*page_size+1||Number(m[2])-Number(m[1])+1!==p.rows.length)fail('Missing or repeated page range');
   return {page:i+1,total:Number(m[3]),captured_at:p.at,documents:p.rows.map(r=>{
    const id=r.id?.match(/^Document (\d+), not selected, checkbox$/)?.[1];
    if(!id||!Array.isArray(r.cells)||r.cells.length!==8||r.cells[3]!=='NOTICE OF FORECLOSURE'||!/^\d+$/.test(r.cells[6]))fail('Unexpected Dallas row layout');
    return {document_id:id,document_number:r.cells[6],document_url:documentURL('Dallas',id),filed_date:mmddyyyy(r.cells[4]),auction_date:r.cells[5]?mmddyyyy(r.cells[5]):null,indexed_address:r.cells[7]};
   })};
  });
 });
 return {schema_version:'1.0',county:'Dallas',window_start,window_end,page_size,scans};
}
export function normalizeCollinCapture(capture){
 if(capture.source!=='https://apps2.collincountytx.gov/ForeclosureNotices/'||capture.page_size!==25||!Number.isInteger(capture.total)||capture.total<1||!Array.isArray(capture.passes)||capture.passes.length!==2)fail('Expected complete Collin visible index captures');
 isoDate(capture.window_start);isoDate(capture.window_end);
 const scans=capture.passes.map(pass=>{
  if(!Array.isArray(pass)||pass.length!==capture.total)fail('Missing Collin rows');
  const pages=[];
  pass.forEach((r,i)=>{
   const page=Math.floor(i/25)+1;
   if(r.page!==page||r.row!==i%25)fail('Collin row order or page gap');
   const id=r.url?.match(/^https:\/\/apps2\.collincountytx\.gov\/ForeclosureNotices\/DetailPage\/(\d+)$/)?.[1];
   const m=typeof r.text==='string'&&r.text.match(/^([\s\S]*?)City:\s*([\s\S]*?)Sale Date:\s*(\d{1,2}\/\d{1,2}\/\d{4})\s*File Date:\s*(\d{1,2}\/\d{1,2}\/\d{4})(?:\s*Property Type:[\s\S]*)?\s*$/);
   if(!id||!m)fail('Unexpected Collin row or missing stable detail URL');
   if(!pages[page-1])pages.push({page,total:capture.total,captured_at:r.captured_at,documents:[]});
   pages[page-1].captured_at=r.captured_at;
   pages[page-1].documents.push({document_id:id,document_number:'',document_url:r.url,filed_date:mmddyyyy(m[4]),auction_date:mmddyyyy(m[3]),indexed_address:m[1].replace(/\s+/g,' ').trim()});
  });
  return pages;
 });
 return {schema_version:'1.0',county:'Collin',window_start:capture.window_start,window_end:capture.window_end,page_size:25,scans};
}
export async function inventoryManifests(capture,now=new Date()){
 const {county,window_start,window_end,page_size,scans}=capture;
 if(capture.schema_version!=='1.0'||!Object.hasOwn(countySources,county))fail('Unsupported inventory source');
 isoDate(window_start);isoDate(window_end);
 const days=(Date.parse(window_end)-Date.parse(window_start))/86400000+1;
 const scheduled=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Chicago'}).format(now);
 if(days<1||days>30||window_end>scheduled)fail('Invalid filing window');
 if(!Number.isInteger(page_size)||page_size<1||page_size>2000||!Array.isArray(scans)||scans.length!==2)fail('Two scans and bounded page size required');
 let previousTime=0;
 const inventories=scans.map(scan=>{
  if(!Array.isArray(scan)||!scan.length||scan.length>2000)fail('Missing or oversized scan');
  const total=scan[0].total;
  if(!Number.isInteger(total)||total<1||total>100000||scan.length!==Math.ceil(total/page_size))fail('Missing pages or unsupported empty capture');
  const ids=new Set();
  return scan.flatMap((p,i)=>{
   const time=Date.parse(p.captured_at);
   if(!Number.isFinite(time)||time<previousTime||time>now.getTime()||now.getTime()-time>24*3600000)fail('Stale, unordered or future capture');
   previousTime=time;
   if(p.page!==i+1||p.total!==total||!Array.isArray(p.documents)||p.documents.length!==Math.min(page_size,total-i*page_size))fail('Page counts changed or page missing');
   return p.documents.map(d=>{
    if(typeof d.document_id!=='string'||!/^\d{1,30}$/.test(d.document_id)||ids.has(d.document_id))fail('Missing or repeated document ID');
    ids.add(d.document_id);
    if(d.document_url!==documentURL(county,d.document_id))fail('Document URL does not bind to county ID');
    isoDate(d.filed_date);if(d.auction_date!==null)isoDate(d.auction_date);
    if(d.filed_date<window_start||d.filed_date>window_end)fail('Filing outside window');
    if(typeof d.indexed_address!=='string'||d.indexed_address.length>2000||typeof d.document_number!=='string'||d.document_number.length>100)fail('Unexpected index text');
    return {document_id:d.document_id,document_number:d.document_number,document_url:d.document_url,filed_date:d.filed_date,auction_date:d.auction_date,indexed_address:d.indexed_address};
   });
  });
 });
 if(canonicalJSON(inventories[0])!==canonicalJSON(inventories[1]))fail('Verification inventory changed');
 const inventoryHash=await sha256(canonicalJSON(capture));
 const records=inventories[0].map(d=>({
  source_record_id:d.document_id,case_number:d.document_number||null,filed_date:d.filed_date,auction_date:d.auction_date,
  property_address:null,unit:null,city:null,state:'TX',zip:null,parcel_id:null,owner_name:null,mailing_address:null,
  amount_owed:null,amount_type:'unknown',source_url:d.document_url,
  raw:{collector:'supervised-foreclosure-index-v1',inventory_sha256:inventoryHash,indexed_address:d.indexed_address,
   index_only:true,filing_stamp_verified:false,identity_verified:false,current_status_checked:false,
   review_flags:'All notice pages, filing stamp, independent situs identity and current sale status require review. Indexed address may describe multiple properties; past auction date does not prove sale outcome.'}
 }));
 // Indexed multi-property strings stay raw; never invent one property from a document.
 const batches=[];const batchCount=Math.ceil(records.length/500);
 const run_id=randomUUID();
 for(let i=0;i<batchCount;i++){
  const chunk=records.slice(i*500,(i+1)*500);
  const payload={schema_version:'1.0',source_key:`tx-${county.toLowerCase()}-pre_foreclosure`,run_id,scheduled_for:scheduled,pulled_at:now.toISOString(),
   source:{state:'TX',county,jurisdiction:county+' County',list_type:'pre_foreclosure',source_url:countySources[county]},
   status:'partial',status_reason:'Two matching index traversals; notice pages, filing stamps, property identity and current status remain unverified. Review-only discovery, not complete foreclosure coverage.',
   lookback_days:days,window_start,window_end,coverage_complete:false,source_as_of:null,batch_index:i,batch_count:batchCount,
   records_sha256:await sha256(canonicalJSON(chunk)),records:chunk};
  if(!(await preflight(payload,now)).valid)fail('Generated manifest failed preflight');
  batches.push(payload);
 }
 return {batches,inventory_sha256:inventoryHash,records:records.length};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 try{
  const [input,output,format]=process.argv.slice(2);
  if(!input||!output||process.argv.length>5||format&&!['--dallas-visible','--collin-visible'].includes(format))fail('Usage: node foreclosure_inventory.mjs capture.json new-output-dir [--dallas-visible|--collin-visible]');
  if(fs.statSync(input).size>10*1024*1024)fail('Inventory exceeds 10 MiB');
  let capture=JSON.parse(fs.readFileSync(input,'utf8'));if(format)capture=format==='--dallas-visible'?normalizeDallasCapture(capture):normalizeCollinCapture(capture);
  const result=await inventoryManifests(capture);
  fs.mkdirSync(output,{mode:0o700});
  fs.writeFileSync(path.join(output,'inventory.json'),JSON.stringify(capture),{mode:0o600,flag:'wx'});
  result.batches.forEach((b,i)=>fs.writeFileSync(path.join(output,`batch-${String(i).padStart(4,'0')}.json`),JSON.stringify(b),{mode:0o600,flag:'wx'}));
  console.log(JSON.stringify({run_id:result.batches[0].run_id,records:result.records,batches:result.batches.length,inventory_sha256:result.inventory_sha256,delivered:false,coverage_complete:false}));
 }catch(e){console.error(e instanceof Error?e.message:'Inventory conversion failed');process.exitCode=1;}
}
