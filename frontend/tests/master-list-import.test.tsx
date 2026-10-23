import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
const mocks=vi.hoisted(()=>({api:vi.fn(),start:vi.fn(),success:vi.fn(),warning:vi.fn(),error:vi.fn()}));
vi.mock('@/lib/api',()=>({apiFetch:mocks.api}));
vi.mock('@/stores/useAutoScoreStore',()=>({useAutoScoreStore:{getState:()=>({start:mocks.start})}}));
vi.mock('sonner',()=>({toast:{success:mocks.success,warning:mocks.warning,error:mocks.error}}));
import { MasterListBuilder } from '@/pages/MasterListBuilder';
import { useMasterListStore } from '@/stores/useMasterListStore';
import { mergeRowInto, type MergedRow } from '@/lib/masterList';
function show(){return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><MasterListBuilder/></MemoryRouter></QueryClientProvider>);}
function outcome(_path:string,init:RequestInit){
  const body=JSON.parse(init.body as string);
  return Promise.resolve(new Response(JSON.stringify({status:'ok',request_id:body.request_id,replayed:false,imported:6,updated:0,
    consolidated_rows:6,skipped:0,scored:6,owner_review:0,scoring_state:'completed'})));
}
beforeEach(()=>{
  vi.clearAllMocks();useMasterListStore.getState().clearAll();
  const rows=new Map<string,MergedRow>();
  for(let i=1;i<=6;i++)mergeRowInto(rows,{property_address:`${i} Master CSV St`,city:'Dallas',state:'TX'},'PropStream');
  useMasterListStore.getState().setMerged([...rows.values()]);mocks.api.mockImplementation(outcome);
});
it('imports every merged property with atomic free scoring and no background scoring start',async()=>{
  show();fireEvent.click(screen.getByRole('button',{name:'Import Directly to Leads'}));
  await waitFor(()=>expect(mocks.success).toHaveBeenCalled());
  const body=JSON.parse(mocks.api.mock.calls[0][1].body);
  expect(body.rows).toHaveLength(6);expect(body).toMatchObject({engine:'rules',score_with_claude:true});
  expect(body.request_id).toBe(useMasterListStore.getState().importRequestId);
  expect(mocks.start).not.toHaveBeenCalled();
  expect(mocks.success.mock.calls[0][0]).toContain('6 scored');
});
it('retains the same request after a lost response and route remount',async()=>{
  mocks.api.mockRejectedValueOnce(new Error('Response lost'));
  const view=show();fireEvent.click(screen.getByRole('button',{name:'Import Directly to Leads'}));
  await waitFor(()=>expect(mocks.error).toHaveBeenCalledWith('Response lost'));
  expect(mocks.api).toHaveBeenCalledTimes(1);view.unmount();show();
  fireEvent.click(screen.getByRole('button',{name:'Import Directly to Leads'}));
  await waitFor(()=>expect(mocks.success).toHaveBeenCalled());
  expect(mocks.api).toHaveBeenCalledTimes(2);
  expect(mocks.api.mock.calls[0][1].body).toBe(mocks.api.mock.calls[1][1].body);
  expect(mocks.start).not.toHaveBeenCalled();
});
it('shows a review warning separately from the confirmed saved count',async()=>{
  mocks.api.mockImplementation(async(path:string,init:RequestInit)=>{
    const response=await outcome(path,init);const value=await response.json();
    return new Response(JSON.stringify({...value,scored:0,scoring_state:'review',warning:'Saved; existing work needs review.'}));
  });
  show();fireEvent.click(screen.getByRole('button',{name:'Import Directly to Leads'}));
  await waitFor(()=>expect(mocks.warning).toHaveBeenCalledWith('Saved; existing work needs review.'));
  expect(mocks.error).not.toHaveBeenCalled();expect(mocks.start).not.toHaveBeenCalled();
});
