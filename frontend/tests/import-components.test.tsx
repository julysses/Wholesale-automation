import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ api: vi.fn(), from: vi.fn(), insert: vi.fn(), score: vi.fn(), defer: false, callbacks: [] as Array<(data: unknown)=>void> }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.api }));
vi.mock('@/lib/supabase', () => ({ supabase: { from: mocks.from } }));
vi.mock('@/stores/useAutoScoreStore', () => ({useAutoScoreStore:{getState:()=>({start:mocks.score})}}));
vi.mock('sonner', () => ({toast:{success:vi.fn(),error:vi.fn()}}));
vi.mock('papaparse', () => ({default:{parse:(_file:File,options:{complete: (data:unknown)=>void})=>{ if(mocks.defer){mocks.callbacks.push(options.complete);return;} options.complete({
  meta:{fields:['Owner Name','Property Address','City','Address','Phone','TAV']},errors:[],data:Array.from({length:6},(_,i)=>({
    'Owner Name':'Synthetic Owner '+i,'Property Address':`${i+1} Test St`,City:'Dallas',Address:`${i+1} Test St`,Phone:'2145550100',TAV:'0',
  })),
}); }}}));
import { LandLeadImportModal } from '@/pages/LandLeads';
import { LeadImportModal } from '@/components/leads/LeadImportModal';
function show(component:React.ReactNode) {
  render(<QueryClientProvider client={new QueryClient()}>{component}</QueryClientProvider>);
  fireEvent.change(document.querySelector('input[type="file"]')!,{target:{files:[new File(['test'],'test.csv',{type:'text/csv'})]}});
}
function landResponse(_path:string,init:RequestInit) {
  const body=JSON.parse(init.body as string);
  return Promise.resolve(new Response(JSON.stringify({receipt:{id:body.request_id,payload:body.rows,result:{imported:body.rows.length,existing:0}},outreach_authorized:false})));
}
beforeEach(()=>{
  vi.clearAllMocks();mocks.defer=false;mocks.callbacks=[];mocks.insert.mockResolvedValue({error:null});mocks.from.mockReturnValue({insert:mocks.insert});mocks.api.mockImplementation(landResponse);
});
it('land import submits every row rather than the five-row preview, through the receipt API',async()=>{
  show(<LandLeadImportModal onClose={()=>{}}/>);
  const button = await screen.findByRole('button',{name:/^Import \d/});
  expect(screen.getAllByText('$0')).toHaveLength(5);
  fireEvent.click(button);
  await waitFor(()=>expect(mocks.api).toHaveBeenCalledTimes(1));
  const [path,init]=mocks.api.mock.calls[0];const body=JSON.parse(init.body);
  expect(path).toBe('/api/land/imports');expect(body.rows).toHaveLength(6);
  expect(body.rows[5]).toMatchObject({owner_name:'Synthetic Owner 5',property_address:'6 Test St',city:'Dallas'});
  expect(body.rows[0].tav).toBe(0);
  expect(body.rows[0]).not.toHaveProperty('dnc');expect(body.rows[0]).not.toHaveProperty('sms_sequence_active');
  expect(await screen.findByText(/6 leads imported/)).toBeInTheDocument();expect(mocks.from).not.toHaveBeenCalled();
});
it('land import retries only on an explicit click with the same receipt reference after a lost response',async()=>{
  mocks.api.mockRejectedValueOnce(new Error('Connection lost; outcome unconfirmed'));
  show(<LandLeadImportModal onClose={()=>{}}/>);
  fireEvent.click(await screen.findByRole('button',{name:/^Import \d/}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Connection lost');
  expect(mocks.api).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button',{name:/Retry original import/}));
  await waitFor(()=>expect(mocks.api).toHaveBeenCalledTimes(2));
  expect(JSON.parse(mocks.api.mock.calls[0][1].body)).toEqual(JSON.parse(mocks.api.mock.calls[1][1].body));
  expect(await screen.findByText(/6 leads imported/)).toBeInTheDocument();
});
it('standalone lead modal routes all rows through reconciliation and reports existing records',async()=>{
  mocks.api.mockImplementation((_path:string,init:RequestInit)=>{const body=JSON.parse(init.body as string); return Promise.resolve(new Response(JSON.stringify({status:'ok',request_id:body.request_id,replayed:false,imported:0,updated:6,skipped:0,scored:0,consolidated_rows:6,owner_review:0,scoring_state:'completed'})));});
  show(<LeadImportModal open onClose={()=>{}}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Import Leads',exact:true}));
  await waitFor(()=>expect(mocks.api).toHaveBeenCalledTimes(1));
  const [path,init]=mocks.api.mock.calls[0];expect(path).toBe('/api/ai/import-master-list');
  expect(JSON.parse(init.body)).toMatchObject({engine:'rules',rows:expect.any(Array)});expect(JSON.parse(init.body).rows).toHaveLength(6);
  expect(await screen.findByText(/6 existing leads reconciled/)).toBeInTheDocument();
  expect(mocks.from).not.toHaveBeenCalled();expect(mocks.score).not.toHaveBeenCalled();
});
it('standalone lead modal exposes an uncertain outcome, refreshes and never auto-retries',async()=>{
  mocks.api.mockRejectedValue(new Error('Connection lost; outcome unconfirmed'));
  show(<LeadImportModal open onClose={()=>{}}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Import Leads',exact:true}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Connection lost');
  expect(mocks.api).toHaveBeenCalledTimes(1);expect(mocks.from).not.toHaveBeenCalled();
});

it('land import ignores an older file reader finishing after the newly selected file',async()=>{
  mocks.defer=true;show(<LandLeadImportModal onClose={()=>{}}/>);
  fireEvent.change(document.querySelector('input[type="file"]')!,{target:{files:[new File(['second'],'second.csv',{type:'text/csv'})]}});
  const parsed=(address:string)=>({meta:{fields:['Owner Name','Property Address','City']},errors:[],data:[{'Owner Name':'Synthetic','Property Address':address,City:'Dallas'}]});
  act(()=>{mocks.callbacks[1](parsed('Current File St'));mocks.callbacks[0](parsed('Stale File St'));});
  fireEvent.click(await screen.findByRole('button',{name:/^Import \d/}));
  await waitFor(()=>expect(mocks.api).toHaveBeenCalledTimes(1));
  expect(JSON.parse(mocks.api.mock.calls[0][1].body).rows[0].property_address).toBe('Current File St');
});

it('standalone modal explicitly retries the original request body after an uncertain response',async()=>{
  mocks.api.mockImplementationOnce(()=>Promise.reject(new Error('Response lost'))).mockImplementation((_path:string,init:RequestInit)=>{
    const body=JSON.parse(init.body as string);return Promise.resolve(new Response(JSON.stringify({status:'ok',request_id:body.request_id,replayed:true,
      imported:6,updated:0,skipped:0,scored:6,consolidated_rows:6,owner_review:0,scoring_state:'completed'})));
  });
  show(<LeadImportModal open onClose={()=>{}}/>);
  fireEvent.click(await screen.findByRole('button',{name:'Import Leads',exact:true}));
  expect(await screen.findByRole('alert')).toHaveTextContent('Response lost');
  expect(mocks.api).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button',{name:'Retry original import'}));
  await waitFor(()=>expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  expect(mocks.api).toHaveBeenCalledTimes(2);
  expect(mocks.api.mock.calls[0][1].body).toEqual(mocks.api.mock.calls[1][1].body);
});
