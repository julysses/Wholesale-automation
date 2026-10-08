import { useQuery } from '@tanstack/react-query';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { supabase } from '@/lib/supabase';
import { queryAll } from '@/lib/queryAll';
import type { DealWrite } from '@/hooks/useDeals';
export function DealHandoffFields({value,onChange}:{value:DealWrite;onChange:(value:DealWrite)=>void}) {
  const {data:owners=[],error:ownersError}=useQuery({queryKey:['handoff_owners'],queryFn:()=>queryAll<{id:string;full_name:string;email:string}>((from,to)=>supabase.from('profiles').select('id,full_name,email').eq('status','approved').order('id').range(from,to))});
  const {data:buyers=[],error:buyersError}=useQuery({queryKey:['handoff_buyers'],queryFn:()=>queryAll<{id:string;first_name:string;last_name:string;company:string}>((from,to)=>supabase.from('buyers').select('id,first_name,last_name,company').order('id').range(from,to))});
  const text = (key: keyof DealWrite, label: string, type='text') => <Input key={key} label={label} type={type} value={String(value[key] ?? '')}
    onChange={e=>onChange({...value,[key]:e.target.value || null})} />;
  return <section aria-label="Deal handoff" className="space-y-3">
    <h4 className="font-semibold">Contract, title and buyer handoff</h4>
    {(ownersError||buyersError)&&<p role="alert">Handoff options could not be loaded. Refresh before assigning owner or buyer.</p>}
    <div className="grid grid-cols-2 gap-3">
      <Select label="Responsible owner" value={value.assigned_to ?? ''} onChange={e=>onChange({...value,assigned_to:e.target.value || null})}
        options={[...(value.assigned_to&&!owners.some(o=>o.id===value.assigned_to)?[{value:value.assigned_to,label:'Current owner'}]:[]),...owners.map(o=>({value:o.id,label:o.full_name||o.email}))]} placeholder="Defaults to creating operator" />
      <Select label="Selected buyer" value={value.buyer_id ?? ''} onChange={e=>onChange({...value,buyer_id:e.target.value || null})}
        options={[...(value.buyer_id&&!buyers.some(b=>b.id===value.buyer_id)?[{value:value.buyer_id,label:'Current buyer'}]:[]),...buyers.map(b=>({value:b.id,label:`${b.first_name} ${b.last_name}${b.company ? ` · ${b.company}` : ''}`}))]} placeholder="No buyer selected" />
      {text('seller_name','Seller name')}
      <Input label="Earnest money" type="number" min="0" value={value.earnest_money ?? ''} onChange={e=>onChange({...value,earnest_money:e.target.value ? Number(e.target.value) : null})} />
      {text('inspection_deadline','Inspection deadline','date')}
      {text('title_contact','Title contact')}
      {text('title_phone','Title phone')}
      {text('psa_doc_url','Signed PSA link (HTTPS)','url')}
      {text('assignment_doc_url','Signed assignment link (HTTPS)','url')}
    </div>
    <p className="text-sm">Inspection and closing dates create assigned review tasks at 5 PM Central. Changing a deadline reopens its review task. Verify revised dates with the owner.</p>
  </section>;
}
