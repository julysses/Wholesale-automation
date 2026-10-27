// Synthetic, in-memory browser fixture. No fetch, credentials or provider calls.
import type { CostImportRequest } from '../../src/lib/costImport';
export class ApiError extends Error { constructor(message:string, public status=409, public rejectedCreate=false, public rejectedCost=false){super(message);} }
export const scope={user:'10000000-0000-4000-8000-000000000001',workspace:'20000000-0000-4000-8000-000000000001',campaign:'30000000-0000-4000-8000-000000000001',intake:'40000000-0000-4000-8000-000000000001'};
export const link={campaign:scope.campaign,review:'50000000-0000-4000-8000-000000000001',external:'123',account:'456'};
let fault='none'; export function setFault(value:string){fault=value;}
const ledger:CostImportRequest[]=[];
export function count(){return ledger.length;}
export async function apiFetch(path:string,init?:RequestInit){
  if(!path.startsWith(`/api/acquisition/workspaces/${scope.workspace}/`)) throw new ApiError('Unknown synthetic scope');
  if(path.endsWith('/cost-evidence') && init?.method==='POST'){
    const request=JSON.parse(String(init.body)) as CostImportRequest;
    const old=ledger.find(row=>row.id===request.id);
    if(old && JSON.stringify(old)!==JSON.stringify(request))throw new ApiError('Synthetic request conflict',409,false,true);
    if(!old){
      if(fault==='reject'){fault='none';throw new ApiError('Synthetic confirmed rejection',409,false,true);}
      const latest=ledger.filter(row=>row.data.date===request.data.date).at(-1);
      if(request.data.expected_revision!==(latest?latest.data.expected_revision+1:0))throw new ApiError('Synthetic stale revision',409,false,true);
      ledger.push(request);
      if(fault==='lost'){fault='none';throw new Error('Synthetic reply lost after save');}
    }
    return {json:async()=>({id:request.id,campaign_id:scope.campaign,revision:request.data.expected_revision+1,duplicate:!!old,execution_authorized:false})};
  }
  if(path.includes(`/campaigns/${scope.campaign}/cost-coverage?`)){
    const params=new URL(path,'http://fixture.invalid').searchParams,start=params.get('start_date')!,end=params.get('end_date')!;
    const days=[];let amount=0n,observed=false;
    for(let day=Date.parse(start);day<=Date.parse(end);day+=86400000){
      const date=new Date(day).toISOString().slice(0,10),row=ledger.filter(item=>item.data.date===date).at(-1);
      if(row?.data.amount_minor!==null && row){amount+=BigInt(row.data.amount_minor);observed=true;}
      days.push({date,coverage:row?.data.coverage??'missing',amount_minor:row?.data.amount_minor==null?null:String(row.data.amount_minor),revision_id:row?.id??null,revision:row?row.data.expected_revision+1:null,evidence_hash:row?.data.evidence_hash??null,observed_at:row?.data.observed_at??null,attribution_current:row?true:null,link_review_id:row?.link_review_id??null});
    }
    const complete=days.filter(day=>day.coverage==='complete').length,reasons=[];
    if(days.some(day=>day.coverage==='missing'))reasons.push('COST_MISSING');
    if(days.some(day=>day.coverage==='partial'))reasons.push('COST_PARTIAL');
    if(days.some(day=>day.coverage==='withdrawn'))reasons.push('COST_WITHDRAWN');
    return {json:async()=>({workspace_id:scope.workspace,campaign_id:scope.campaign,start_date:start,end_date:end,as_of:new Date().toISOString(),currency:'USD',reporting_timezone:'America/Chicago',status:complete===days.length?'complete':'incomplete',reason_codes:reasons,total_cost_minor:complete===days.length?String(amount):null,observed_cost_minor:observed?String(amount):null,days,complete_days:complete,requested_days:days.length,execution_authorized:false,cost_per_lead_minor:null,qualified_cost_per_lead_minor:null,denominator_status:'NOT_RECONCILED',projection_version:'acquisition-cost-coverage-v1',evidence_basis:'reviewed_import',minor_unit_exponent:2,attribution_checked_at:new Date().toISOString()})};
  }
  throw new ApiError('Unknown synthetic request');
}
