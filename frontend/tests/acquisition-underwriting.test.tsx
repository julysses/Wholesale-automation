import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AcquisitionUnderwriting } from '../src/pages/AcquisitionUnderwriting';
const mock=vi.hoisted(()=>({fetch:vi.fn(),fail:false,pendingHistory:false}));
vi.mock('@/lib/api',()=>({apiFetch:mock.fetch,ApiError:class extends Error{status=409;}}));
const analysis={id:'saved-analysis',acquisition_revision:1,acquisition_status:'calculated',acquisition_strategy:'fix_and_flip',acquisition_outputs:{cases:{base:{proposed_offer_range:{low:'120000',high:'150000'}}}}};
beforeEach(()=>{mock.fail=false;mock.pendingHistory=false;mock.fetch.mockReset();mock.fetch.mockImplementation(async(path:string,init?:RequestInit)=>{
  let value:unknown=[];
  if(init?.method==='POST'){
    if(mock.fail){mock.fail=false;throw new Error('network');}
    const body=JSON.parse(String(init.body));
    value=path.endsWith('/offers')?{id:body.id}:path.endsWith('/preview')?{status:'incomplete'}:{analysis:{...analysis,id:body.id,acquisition_status:'pending'},calculation:{status:'pending'}};
  }else if(path.includes('/leads?'))value=[{lead_id:'l',property_id:'p',property_address:'Fixture home',city:'Dallas'}];
  else if(path.includes('/scenarios?'))value=[mock.pendingHistory?{...analysis,acquisition_status:'pending',acquisition_inputs:{cases:{base:{strategy:'fix_and_flip'}}}}:analysis];
  return {json:async()=>value};
});});
async function open(){render(<QueryClientProvider client={new QueryClient()}><AcquisitionUnderwriting userId="u" workspace="w" onProposed={()=>{}}/></QueryClientProvider>);fireEvent.click(screen.getByText('Underwrite a property and propose an offer'));fireEvent.change(await screen.findByLabelText('Property'),{target:{value:'l'}});await screen.findByText('Saved scenarios');}
it('saves sourced inputs with explicit cases and leaves pending calculations pending',async()=>{
  await open();fireEvent.click(screen.getByText('New underwriting scenario'));fireEvent.click(screen.getByText('base case'));
  fireEvent.change(screen.getByLabelText('base: repairs value'),{target:{value:'0'}});fireEvent.change(screen.getByLabelText('base: repairs source'),{target:{value:'Contractor quote'}});
  fireEvent.click(screen.getByRole('button',{name:'Save scenario'}));await screen.findByText(/Inputs saved; calculation is pending/);
  const post=mock.fetch.mock.calls.find(call=>call[1]?.method==='POST');const body=JSON.parse(post![1].body);
  expect(body.inputs.cases.base.repairs.value).toBe('0');expect(body.inputs.cases.downside.repairs).toBeUndefined();expect(body.outputs).toBeUndefined();
  expect(screen.getByRole('button',{name:'Retry same scenario'})).toBeEnabled();
});
it('proposes only the selected saved revision and retries an unknown outcome with the same payload',async()=>{
  await open();fireEvent.click(await screen.findByRole('button',{name:/Revision 1/}));
  fireEvent.change(screen.getByLabelText('Proposed amount (USD)'),{target:{value:'140000.00'}});fireEvent.change(screen.getByLabelText('Proposal rationale'),{target:{value:'Documented case'}});
  mock.fail=true;fireEvent.click(screen.getByRole('button',{name:'Create proposal for review'}));fireEvent.click(await screen.findByRole('button',{name:'Retry same proposal'}));await screen.findByText(/Proposal saved for review/);
  const posts=mock.fetch.mock.calls.filter(call=>call[1]?.method==='POST');expect(posts).toHaveLength(2);expect(posts[0][1].body).toBe(posts[1][1].body);
  const body=JSON.parse(posts[0][1].body);expect(body.analysis_id).toBe('saved-analysis');expect(body.case).toBe('base');expect(body.amount).toBe('140000.00');expect(body.approved_by).toBeUndefined();
});

it('resumes pending history with the original reference and stored inputs',async()=>{
  mock.pendingHistory=true;await open();fireEvent.click(await screen.findByRole('button',{name:/Revision 1/}));
  expect(screen.getByRole('button',{name:'Create proposal for review'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Resume saved calculation'}));await screen.findByText(/Calculation remains pending/);
  const request=mock.fetch.mock.calls.find(call=>call[1]?.method==='POST');const body=JSON.parse(request![1].body);
  expect(body.id).toBe('saved-analysis');expect(body.inputs).toEqual({cases:{base:{strategy:'fix_and_flip'}}});
});
