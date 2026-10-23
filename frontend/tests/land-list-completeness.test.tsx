import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { LandLead } from '@/types';
const mocks=vi.hoisted(()=>({from:vi.fn(),select:vi.fn(),order:vi.fn(),read:vi.fn(),api:vi.fn()}));
vi.mock('@/lib/supabase',()=>({supabase:{from:mocks.from}}));
vi.mock('@/lib/api',()=>({apiFetch:mocks.api}));
vi.mock('@/components/land/LotInbox',()=>({LotInbox:()=>null}));
vi.mock('@/components/land/LandBuyerHub',()=>({LandBuyerHub:()=> <p>Buyer hub</p>}));
vi.mock('@/components/land/SevenMustsForm',()=>({SevenMustsForm:({lead}:{lead:LandLead})=><p>Vetting {lead.property_address}</p>}));
vi.mock('@/components/land/QuickCompCalculator',()=>({QuickCompCalculator:({lead}:{lead:LandLead})=><p>Comping {lead.property_address}</p>}));
vi.mock('papaparse',()=>({default:{parse:(_file:File,options:{complete:(value:unknown)=>void})=>options.complete({errors:[],meta:{fields:['Owner Name','Property Address','City']},data:[{'Owner Name':'Synthetic Import Owner','Property Address':'Fresh Imported Lot',City:'Dallas'}]})}}));
import { LandLeads } from '@/pages/LandLeads';
const row=(n:number):LandLead=>({id:`land-${String(n).padStart(5,'0')}`,created_at:'2026-10-22T12:00:00Z',updated_at:'2026-10-22T12:00:00Z',
  owner_name:'Synthetic Owner '+n,property_address:`${n} Test St`,city:'Dallas',state:'TX',source:'csv_import',status:'new',
  water_source:'unknown',sewage:'unknown',infill_lot:n%2===0,contact_attempts:0,dnc:false,sms_sequence_active:false,
} as LandLead);
let records:LandLead[]=[];
let clients:QueryClient[]=[];
function show(){
  const client=new QueryClient({defaultOptions:{queries:{retry:false}}});clients.push(client);
  render(<QueryClientProvider client={client}><LandLeads/></QueryClientProvider>);return client;
}
beforeEach(()=>{
  vi.clearAllMocks();records=Array.from({length:6},(_,i)=>row(i+1));clients=[];
  mocks.read.mockImplementation(async(from:number,to:number)=>({data:records.slice(from,Math.min(to+1,from+2)),error:null,count:records.length}));
  mocks.from.mockImplementation(()=>{
    const query={select:(...args:unknown[])=>{mocks.select(...args);return query;},order:(...args:unknown[])=>{mocks.order(...args);return query;},eq:()=>query,
      range:(from:number,to:number)=>mocks.read(from,to),then:(resolve:(value:unknown)=>unknown)=>Promise.resolve(mocks.read(0,999)).then(resolve)};
    return query;
  });
});
afterEach(()=>clients.forEach(client=>client.clear()));
it('loads beyond the API row cap, shows complete totals, paginates cards and finds late imported records',async()=>{
  records=Array.from({length:1003},(_,i)=>row(i+1));records[1000].status='comped';records[1000].vetting_passed=true;
  records[1001].status='under_contract';records[1002].status='dead';records[1002].vetting_passed=true;
  mocks.read.mockImplementation(async(from:number,to:number)=>({data:records.slice(from,Math.min(to+1,from+1000)),error:null,count:records.length}));
  show();expect(await screen.findByText('1,003 leads · 501 infill lots · 1 under contract')).toBeInTheDocument();
  expect(mocks.read.mock.calls).toEqual([[0,499],[500,999],[1000,1499],[1003,1502]]);
  expect(mocks.select).toHaveBeenCalledWith('*',{count:'exact'});expect(mocks.order).toHaveBeenCalledWith('id',{ascending:true});
  expect(screen.getByLabelText('Land record pages')).toHaveTextContent('1–25 of 1,003');
  expect(screen.queryByText('26 Test St')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Next land page'}));expect(screen.getByText('26 Test St')).toBeInTheDocument();
  fireEvent.change(screen.getByRole('searchbox',{name:'Search land records'}),{target:{value:'1001 Test St'}});
  expect(screen.getByText('1001 Test St')).toBeInTheDocument();expect(screen.queryByText('26 Test St')).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole('searchbox',{name:'Search land records'}),{target:{value:''}});
  fireEvent.change(screen.getByLabelText('Land status'),{target:{value:'under_contract'}});
  expect(screen.getByText('1002 Test St')).toBeInTheDocument();expect(mocks.read).toHaveBeenCalledTimes(4);
});
it('never reports a partial read failure as an empty list or zero funnel',async()=>{
  mocks.read.mockImplementation(async(from:number)=>from ? {data:null,error:{message:'Later page interrupted'},count:null}:{data:records.slice(0,2),error:null,count:6});
  show();expect(await screen.findByRole('alert')).toHaveTextContent('Later page interrupted');
  expect(screen.getByText('Land totals unavailable')).toBeInTheDocument();expect(screen.queryByText('No land leads yet')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'7 Musts Vetting'}));expect(screen.queryByText('No leads awaiting vetting')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Quick-Comp'}));expect(screen.queryByText('No vetted leads ready for comping')).not.toBeInTheDocument();
});
it('keeps the last complete dataset on refresh failure and replaces it only after a complete retry',async()=>{
  const client=show();expect(await screen.findByText('6 leads · 3 infill lots · 0 under contract')).toBeInTheDocument();
  mocks.read.mockImplementation(async(from:number)=>from ? {data:null,error:{message:'Later page interrupted'},count:null}:{data:records.slice(0,2),error:null,count:6});
  await act(()=>client.invalidateQueries({queryKey:['land_leads']}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Showing previously loaded records');
  expect(screen.getByText('6 Test St')).toBeInTheDocument();expect(screen.getByText(/6 leads · 3 infill lots/)).toBeInTheDocument();
  records.push(row(7));mocks.read.mockImplementation(async(from:number,to:number)=>({data:records.slice(from,Math.min(to+1,from+2)),error:null,count:7}));
  fireEvent.click(screen.getByRole('button',{name:'Retry loading land records'}));
  expect(await screen.findByText('7 leads · 3 infill lots · 0 under contract')).toBeInTheDocument();
  await waitFor(()=>expect(screen.queryByRole('alert')).not.toBeInTheDocument());
});
it('refuses an unconfirmed database count',async()=>{
  mocks.read.mockResolvedValue({data:records,error:null,count:null});show();
  expect(await screen.findByRole('alert')).toHaveTextContent('count could not be confirmed');
  expect(screen.queryByText('1 Test St')).not.toBeInTheDocument();
});
it('refuses changing counts or duplicate identities across pages',async()=>{
  mocks.read.mockImplementation(async(from:number)=>({data:records.slice(from,from+2),error:null,count:from?7:6}));
  const client=show();expect(await screen.findByRole('alert')).toHaveTextContent('changed while loading');
  mocks.read.mockImplementation(async(from:number)=>({data:from===2?[records[0],records[3]]:records.slice(from,from+2),error:null,count:6}));
  await act(()=>client.invalidateQueries({queryKey:['land_leads']}));
  expect(await screen.findByRole('alert')).toHaveTextContent('changed while loading');
  expect(screen.queryByText('1 Test St')).not.toBeInTheDocument();
});
it('shows a verified empty state after a complete zero-count response',async()=>{
  records=[];show();expect(await screen.findByText('No land leads yet')).toBeInTheDocument();
  expect(screen.getByText('0 leads · 0 infill lots · 0 under contract')).toBeInTheDocument();expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
it('refreshes complete funnel totals immediately after the import receipt is confirmed',async()=>{
  mocks.api.mockImplementation(async(_path:string,init:RequestInit)=>{
    const body=JSON.parse(init.body as string);records.push({...row(7),property_address:'Fresh Imported Lot'});
    return new Response(JSON.stringify({receipt:{id:body.request_id,payload:body.rows,result:{imported:1,existing:0}},outreach_authorized:false}));
  });
  show();expect(await screen.findByText('6 leads · 3 infill lots · 0 under contract')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Import CSV',exact:true}));
  fireEvent.change(document.querySelector('input[type="file"]')!,{target:{files:[new File(['test'],'import.csv',{type:'text/csv'})]}});
  fireEvent.click(await screen.findByRole('button',{name:'Import 1 leads'}));
  expect(await screen.findByText(/1 leads imported/)).toBeInTheDocument();
  expect(await screen.findByText('7 leads · 3 infill lots · 0 under contract')).toBeInTheDocument();
});
it('keeps dead records out of the comping workflow even when other vetted records exist',async()=>{
  records[4].vetting_passed=true;records[5].vetting_passed=true;records[5].status='dead';show();
  await screen.findByText('6 leads · 3 infill lots · 0 under contract');fireEvent.click(screen.getByRole('button',{name:'Quick-Comp'}));
  expect(screen.getByText('Comping 5 Test St')).toBeInTheDocument();expect(screen.queryByText('Comping 6 Test St')).not.toBeInTheDocument();
});
it('stops a range-ignoring response at the first repeated identity',async()=>{
  const repeated={data:records.slice(0,2),error:null,count:6};
  mocks.read.mockResolvedValueOnce(repeated).mockResolvedValueOnce(repeated).mockResolvedValueOnce(repeated)
    .mockResolvedValueOnce({data:[],error:null,count:6});
  show();expect(await screen.findByRole('alert')).toHaveTextContent('changed while loading');
  expect(mocks.read).toHaveBeenCalledTimes(2);expect(screen.queryByText('1 Test St')).not.toBeInTheDocument();
});
