// Synthetic browser adapter. No fetch, credentials, database or provider calls.
export class ApiError extends Error { constructor(message:string, public status=409){super(message);} }
export const scope={user:'10000000-0000-4000-8000-000000000001',workspace:'20000000-0000-4000-8000-000000000001',campaign:'30000000-0000-4000-8000-000000000001'};
type Draft={id:string;template_id:string;expected_version:number;name:string;format:string;tracking_mode:string;body:string};
const ledgerKey='synthetic-mail-ledger:v1';
function ledger():Draft[]{return JSON.parse(sessionStorage.getItem(ledgerKey)??'[]');}
let fault='none'; export function setFault(value:string){fault=value;}
export function count(){return ledger().length;}
export async function apiFetch(path:string,init?:RequestInit){
  const root=`/api/acquisition/workspaces/${scope.workspace}`;
  if(path===`${root}/memberships`)return {json:async()=>[{workspace_id:scope.workspace,user_id:scope.user,status:'active',role:'operator'}]};
  const endpoint=`${root}/campaigns/${scope.campaign}/mail-templates`;
  if(path===endpoint && init?.method==='POST'){
    const request=JSON.parse(String(init.body)) as Draft,rows=ledger(),old=rows.find(row=>row.id===request.id);
    if(old && JSON.stringify(old)!==JSON.stringify(request))throw new ApiError('Synthetic request conflict');
    if(!old){
      if(fault==='reject'){fault='none';throw new ApiError('Synthetic confirmed rejection');}
      const latest=rows.filter(row=>row.template_id===request.template_id).at(-1);
      if(request.expected_version!==(latest?latest.expected_version+1:0))throw new ApiError('Synthetic stale version');
      sessionStorage.setItem(ledgerKey,JSON.stringify([...rows,request]));
      if(fault==='lost'){fault='none';throw new Error('Synthetic response lost after save');}
    }
    return {json:async()=>({id:request.id,workspace_id:scope.workspace,template_id:request.template_id,version:request.expected_version+1,status:'draft',duplicate:!!old,execution_authorized:false})};
  }
  if(path.startsWith(`${endpoint}?`)){
    const params=new URL(path,'http://fixture.invalid').searchParams,after=params.get('after'),limit=Number(params.get('limit'));
    const rows=ledger().filter(row=>!after || row.id>after).sort((a,b)=>a.id.localeCompare(b.id)),page=rows.slice(0,limit);
    return {json:async()=>({items:page.map(row=>({id:row.id,workspace_id:scope.workspace,campaign_id:scope.campaign,acquisition_template_id:row.template_id,acquisition_template_version:row.expected_version+1,name:row.name,primary_text:row.body,acquisition_mail_format:row.format,acquisition_tracking_mode:row.tracking_mode,status:'draft'})),next_after:rows.length>limit?page.at(-1)!.id:null})};
  }
  throw new ApiError('Unknown synthetic request');
}
