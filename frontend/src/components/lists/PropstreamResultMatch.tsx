import {useRef,useState} from 'react';
import Papa from 'papaparse';
import {Button} from '@/components/ui/button';
import {readResultCsv,matchPropstreamResults,type CsvRow,type ResultColumns} from '@/lib/propstreamResultMatch';
const labels:Record<keyof ResultColumns,string>={owner:'Owner full name',address:'Property street address (including unit)',city:'Property city',state:'Property state',zip:'Property ZIP',phone:'Returned phone',email:'Returned email',dnc:'DNC / suppression flag',phone2:'Returned phone 2',phone3:'Returned phone 3',phone4:'Returned phone 4',phone5:'Returned phone 5',email2:'Returned email 2',email3:'Returned email 3',email4:'Returned email 4',email5:'Returned email 5'};
const empty:ResultColumns={owner:'',address:'',city:'',state:'',zip:'',phone:'',email:'',dnc:''};
function download(name:string,rows:object[]){const u=URL.createObjectURL(new Blob([Papa.unparse(rows,{escapeFormulae:true})],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=u;a.download=name;a.click();URL.revokeObjectURL(u);}
export function PropstreamResultMatch(){
 const generation=useRef({manifest:0,provider:0});
 const [manifest,setManifest]=useState<CsvRow[]>([]);const [provider,setProvider]=useState<CsvRow[]>([]);const [headers,setHeaders]=useState<string[]>([]);const [columns,setColumns]=useState<ResultColumns>(empty);const [result,setResult]=useState<ReturnType<typeof matchPropstreamResults>|null>(null);const [error,setError]=useState('');
 async function load(file:File|undefined,kind:'manifest'|'provider'){
  const current=++generation.current[kind];setResult(null);setError('');if(kind==='manifest')setManifest([]);else{setProvider([]);setHeaders([]);setColumns(empty);}if(!file)return;
  try{if(file.size>5_000_000)throw new Error('CSV limit is 5 MB.');const parsed=readResultCsv(await file.text());if(current!==generation.current[kind])return;if(kind==='manifest')setManifest(parsed.rows);else{setProvider(parsed.rows);setHeaders(parsed.columns);}}catch(e){if(current===generation.current[kind])setError(e instanceof Error?e.message:'CSV could not be read');}
 }
 return <details className="border rounded p-3"><summary className="font-semibold">Match a PropStream result file in bulk</summary>
 <p>Upload the current “Import matched results” sheet and the provider’s CSV. Map columns once. Exact owner and full property identity must agree; reordered rows are supported. Ambiguous records and suppression flags stay in the exception file.</p>
 <label className="block">WholesaleOS reconciliation sheet <input type="file" accept=".csv" onChange={e=>{void load(e.target.files?.[0],'manifest');e.target.value='';}}/></label>
 <label className="block">PropStream result CSV <input type="file" accept=".csv" onChange={e=>{void load(e.target.files?.[0],'provider');e.target.value='';}}/></label>
 {!!headers.length&&<div className="grid grid-cols-2 gap-2">{(Object.keys(labels) as (keyof ResultColumns)[]).map(k=><label key={k}>{labels[k]}<select className="block border rounded w-full" value={columns[k]||''} onChange={e=>{setColumns(v=>({...v,[k]:e.target.value}));setResult(null);}}><option value="">Select column</option>{headers.map(h=><option key={h} value={h}>{h}</option>)}</select></label>)}</div>}
 <Button disabled={!manifest.length||!provider.length} onClick={()=>{setResult(null);setError('');try{setResult(matchPropstreamResults(manifest,provider,columns));}catch(e){setError(e instanceof Error?e.message:'Matching failed');}}}>Match all returned rows</Button>
 {error&&<p role="alert">{error}</p>}{result&&<div role="status"><p>{result.matched.length} matched leads · {result.held.length} held leads · {result.exceptions.length} provider rows needing review</p>
 <Button disabled={!result.matched.length} onClick={()=>download('matched-propstream-results.csv',result.matched)}>Download matched results</Button>
 <Button disabled={!result.held.length} onClick={()=>download('propstream-held-leads.csv',result.held)}>Download held leads</Button>
 <Button disabled={!result.exceptions.length} onClick={()=>download('propstream-provider-exceptions.csv',result.exceptions)}>Download provider exceptions</Button>
 <p>Confirm the receipt, actual per-lead charge and matches in the generated sheet, then import it in step 4. Missing rows are not treated as no-match results. Matching does not authorize outreach.</p></div>}
 </details>;
}
