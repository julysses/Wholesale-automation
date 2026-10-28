// Synthetic browser adapter only. No network, credentials, database or provider access.
export class ApiError extends Error {constructor(message:string, public status=409){super(message);}}
export const scope={user:'10000000-0000-4000-8000-000000000001',workspace:'20000000-0000-4000-8000-000000000001',campaign:'30000000-0000-4000-8000-000000000001'};
const destination='40000000-0000-4000-8000-000000000001',ledgerKey='synthetic-mail-destination-ledger:v1';
type Review={id:string;expected_version:number;action:string;note:string;mode?:string;value?:string;verification_ref?:string;verification_hash?:string;verified_at?:string;expires_at?:string};
type Projection={id:string;workspace_id:string;campaign_id:string;destination_id:string;version:number;action:string;mode:string;value:string;verification_ref:string;verification_hash:string;verified_at:string;expires_at:string};
type Entry={destination_id:string;review:Review;projection:Projection};
const seed:Review={id:'50000000-0000-4000-8000-000000000001',expected_version:0,action:'approved',note:'Synthetic controlled destination and routing evidence.',mode:'phone',value:'+12125550100',verification_ref:'60000000-0000-4000-8000-000000000001',verification_hash:'a'.repeat(64),verified_at:'2026-01-01T00:00:00Z',expires_at:'2099-01-01T00:00:00Z'};
function project(destinationId:string,review:Review,previous?:Projection):Projection{return {...previous,...review,workspace_id:scope.workspace,campaign_id:scope.campaign,destination_id:destinationId,version:review.expected_version+1} as Projection;}
function ledger():Entry[]{const raw=sessionStorage.getItem(ledgerKey);if(raw)return JSON.parse(raw);const rows=[{destination_id:destination,review:seed,projection:project(destination,seed)}];sessionStorage.setItem(ledgerKey,JSON.stringify(rows));return rows;}
let fault='none',role='owner';export function setFault(value:string){fault=value;}export function setRole(value:string){role=value;}export function count(){return ledger().length;}
export async function apiFetch(path:string,init?:RequestInit){
 const root=`/api/acquisition/workspaces/${scope.workspace}`,endpoint=`${root}/campaigns/${scope.campaign}/mail-destinations`;
 if(path===`${root}/memberships`)return {json:async()=>[{workspace_id:scope.workspace,user_id:scope.user,status:'active',role}]};
 if(path.startsWith(`${endpoint}/`) && path.endsWith('/reviews') && init?.method==='POST'){
  if(role!=='owner')throw new ApiError('Synthetic reviewer role denied',403);
  const id=path.split('/').at(-2)!,review=JSON.parse(String(init.body)) as Review,rows=ledger(),old=rows.find(r=>r.review.id===review.id);
  if(old && (old.destination_id!==id || JSON.stringify(old.review)!==JSON.stringify(review)))throw new ApiError('Synthetic request conflict');
  if(!old){
   if(fault==='reject'){fault='none';throw new ApiError('Synthetic rejection');}
   const latest=rows.filter(r=>r.destination_id===id).at(-1)?.projection;
   if(review.expected_version!==(latest?.version??0))throw new ApiError('Synthetic version conflict');
   if(review.action==='withdrawn' && (!latest || latest.action==='withdrawn'))throw new ApiError('No current synthetic approval');
   rows.push({destination_id:id,review,projection:project(id,review,latest)});sessionStorage.setItem(ledgerKey,JSON.stringify(rows));
   if(fault==='lost'){fault='none';throw new Error('Synthetic committed response lost');}
  }
  return {json:async()=>({review_id:review.id,workspace_id:scope.workspace,destination_id:id,version:review.expected_version+1,duplicate:!!old,execution_authorized:false})};
 }
 if(path.startsWith(`${endpoint}?`)){
  const params=new URL(path,'http://fixture.invalid').searchParams,after=params.get('after'),limit=Number(params.get('limit'));
  const rows=ledger().map(r=>r.projection).filter(r=>!after || r.id>after).sort((a,b)=>a.id.localeCompare(b.id)),page=rows.slice(0,limit);
  return {json:async()=>({items:page,next_after:rows.length>limit?page.at(-1)!.id:null})};
 }
 if(path.startsWith(`${endpoint}/`)){
  const id=path.slice(endpoint.length+1),latest=ledger().filter(r=>r.destination_id===id).at(-1)?.projection??null,now=new Date().toISOString();
  const current=!!latest && latest.action==='approved' && Date.parse(latest.verified_at)<=Date.parse(now) && Date.parse(now)<Date.parse(latest.expires_at);
  return {json:async()=>({workspace_id:scope.workspace,campaign_id:scope.campaign,destination_id:id,version:latest?.version??0,latest_review:latest,status:!latest?'pending_review':latest.action==='withdrawn'?'withdrawn':current?'approved':'requires_review',review_current:current,execution_authorized:false,checked_at:now})};
 }
 throw new ApiError('Unknown synthetic route');
}
