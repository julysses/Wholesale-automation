import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
const mocks=vi.hoisted(()=>({api:vi.fn()}));
vi.mock('@/lib/api',()=>({apiFetch:mocks.api}));
import { CsvScoringProgress } from '@/components/leads/CsvScoringProgress';
const id='00000000-0000-4000-8000-000000000777';
function progress(scored=0,remaining=60,state='pending',held=0,inflight=0){
 return {status:'ok',request_id:id,scoring_eligible:60,scoring_state:state,scored,scoring_remaining:remaining,scoring_held:held,scoring_in_flight:inflight};
}
function response(value:unknown){return Promise.resolve(new Response(JSON.stringify(value)));}
function show(ref=id){render(<QueryClientProvider client={new QueryClient()}><CsvScoringProgress importId={ref}/></QueryClientProvider>);}
beforeEach(()=>{vi.clearAllMocks();mocks.api.mockImplementation(()=>response(progress()));});
it('reads saved progress without starting AI and continues only on explicit clicks',async()=>{
 let scored=0;
 mocks.api.mockImplementation((_path:string,init:RequestInit)=>{
  if(init.method==='POST')scored=Math.min(60,scored+25);
  return response(progress(scored,60-scored,scored===60?'completed':'pending'));
 });
 show();
 const next=await screen.findByRole('button',{name:'Continue AI scoring (paid)'});
 expect(next).toBeEnabled();expect(mocks.api).toHaveBeenCalledTimes(1);
 expect(mocks.api.mock.calls[0][1].method).toBe('GET');
 fireEvent.click(next);
 await waitFor(()=>expect(mocks.api).toHaveBeenCalledTimes(2));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Continue AI scoring (paid)'})).toBeEnabled());
 expect(mocks.api.mock.calls.filter(([,init])=>init.method==='POST')).toHaveLength(1);
 fireEvent.click(screen.getByRole('button',{name:'Continue AI scoring (paid)'}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Continue AI scoring (paid)'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Continue AI scoring (paid)'}));
 expect(await screen.findByText('AI scoring complete.')).toBeInTheDocument();
 expect(mocks.api.mock.calls.filter(([,init])=>init.method==='POST')).toHaveLength(3);
 expect(screen.queryByRole('button',{name:'Continue AI scoring (paid)'})).not.toBeInTheDocument();
});
it('keeps last confirmed totals after an unknown continuation and requires refresh',async()=>{
 mocks.api.mockImplementation((_path:string,init:RequestInit)=>init.method==='POST'
  ?Promise.reject(new Error('Response lost')):response(progress(25,35)));
 show();fireEvent.click(await screen.findByRole('button',{name:'Continue AI scoring (paid)'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Response lost');
 expect(screen.getByText('Showing last confirmed progress.')).toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Continue AI scoring (paid)'})).toBeDisabled();
 expect(mocks.api.mock.calls.filter(([,init])=>init.method==='POST')).toHaveLength(1);
 mocks.api.mockImplementation(()=>response(progress(25,10,'submitting',0,25)));
 fireEvent.click(screen.getByRole('button',{name:'Refresh scoring progress'}));
 expect(await screen.findByText(/A batch was submitted/)).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Continue AI scoring (paid)'})).not.toBeInTheDocument();
 expect(mocks.api.mock.calls.filter(([,init])=>init.method==='POST')).toHaveLength(1);
});
it('never treats unavailable progress as zero or starts a model request',async()=>{
 mocks.api.mockRejectedValue(new Error('Progress unavailable'));
 show();expect(await screen.findByRole('alert')).toHaveTextContent('Progress unavailable');
 expect(screen.queryByText('Scored')).not.toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Continue AI scoring (paid)'})).not.toBeInTheDocument();
 expect(mocks.api).toHaveBeenCalledTimes(1);
});
it('shows partial completion and held batches without permitting another paid request',async()=>{
 mocks.api.mockImplementation(()=>response(progress(25,10,'review',25)));
 show();expect(await screen.findByText(/This import needs review/)).toBeInTheDocument();
 expect(screen.getByText('Held for review')).toBeInTheDocument();
 expect(screen.queryByRole('button',{name:'Continue AI scoring (paid)'})).not.toBeInTheDocument();
 expect(mocks.api).toHaveBeenCalledTimes(1);
});
it('rejects an uncorrelated progress response',async()=>{
 mocks.api.mockImplementation(()=>response({...progress(),request_id:crypto.randomUUID()}));
 show();expect(await screen.findByRole('alert')).toHaveTextContent('could not be confirmed');
 expect(screen.queryByRole('button',{name:'Continue AI scoring (paid)'})).not.toBeInTheDocument();
});
it('does not call the API for an invalid import link',()=>{
 show('not-a-reference');expect(screen.getByRole('alert')).toHaveTextContent('invalid');
 expect(mocks.api).not.toHaveBeenCalled();
});

it('scores all remaining batches after one explicit action and never repeats a completed batch',async()=>{
 let scored=0;
 mocks.api.mockImplementation((_path:string,init:RequestInit)=>{
  if(init.method==='POST')scored=Math.min(60,scored+25);
  return response(progress(scored,60-scored,scored===60?'completed':'pending'));
 });
 show();fireEvent.click(await screen.findByRole('button',{name:'Score all remaining (paid)'}));
 expect(await screen.findByText('AI scoring complete.')).toBeInTheDocument();
 expect(mocks.api.mock.calls.filter(([,init])=>init.method==='POST')).toHaveLength(3);
});
it('pauses after the current batch without cancelling its saved outcome or starting the next one',async()=>{
 let finish:((value:Response)=>void)|undefined;
 mocks.api.mockImplementation((_path:string,init:RequestInit)=>init.method==='GET'?response(progress()):new Promise<Response>(resolve=>{finish=resolve;}));
 show();fireEvent.click(await screen.findByRole('button',{name:'Score all remaining (paid)'}));
 fireEvent.click(await screen.findByRole('button',{name:'Pause after current batch'}));
 finish!(new Response(JSON.stringify(progress(25,35))));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Score all remaining (paid)'})).toBeEnabled());
 expect(mocks.api.mock.calls.filter(([,init])=>init.method==='POST')).toHaveLength(1);
 expect(screen.queryByText('AI scoring complete.')).not.toBeInTheDocument();
});
it('stops an all-remaining run on an uncertain batch without automatically advancing',async()=>{
 let requests=0;
 mocks.api.mockImplementation((_path:string,init:RequestInit)=>{
  if(init.method==='GET')return response(progress());
  requests++;
  return requests===1?response(progress(25,35)):Promise.reject(new Error('Second batch response lost'));
 });
 show();fireEvent.click(await screen.findByRole('button',{name:'Score all remaining (paid)'}));
 expect(await screen.findByRole('alert')).toHaveTextContent('Second batch response lost');
 expect(screen.getByRole('button',{name:'Score all remaining (paid)'})).toBeDisabled();
 expect(mocks.api.mock.calls.filter(([,init])=>init.method==='POST')).toHaveLength(2);
});
