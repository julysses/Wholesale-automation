import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {beforeEach,expect,it,vi} from 'vitest';
const mocks=vi.hoisted(()=>({fetch:vi.fn(),admin:true}));
vi.mock('@/lib/api',()=>({apiFetch:mocks.fetch}));
vi.mock('@/hooks/useProfile',()=>({useProfile:()=>({isAdmin:mocks.admin,profile:{id:'00000000-0000-4000-8000-000000000001'}})}));
import {PropstreamHandoff} from '@/components/lists/PropstreamHandoff';
const lead='00000000-0000-4000-8000-000000000002',request='00000000-0000-4000-8000-000000000010';
const row={lead_id:lead,county:'Dallas',address_std:'Synthetic verified property',city:'Dallas',zip:'75201',stage:'reserved',signal_id:'00000000-0000-4000-8000-000000000005',signal_hash:'b'.repeat(32),auction_date:'2026-12-01',input_hash:'a'.repeat(64),input:{owner_name:'Synthetic'},request:{id:request,state:'reserved',input_hash:'a'.repeat(64),reserved_cents:50},contacts:[],handoff:null};
const snapshot=(items=[row])=>({items,total:items.length,total_budget:{remaining_cents:4950,committed_cents:50}});
function show(){render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><PropstreamHandoff/></QueryClientProvider>);}
beforeEach(()=>{sessionStorage.clear();vi.resetAllMocks();mocks.admin=true;mocks.fetch.mockResolvedValue({json:async()=>snapshot()});});
it('requires a stable saved action for start and preserves it on an uncertain response',async()=>{
 mocks.fetch.mockImplementation(async(url,options)=>{if(options?.method==='POST')throw new Error('timeout');return {json:async()=>snapshot()};});
 show();await screen.findByText(/Synthetic verified property/);fireEvent.click(screen.getByText(/Synthetic verified property/));
 fireEvent.click(screen.getByRole('button',{name:'Start one PropStream handoff'}));
 await screen.findByRole('alert');
 const first=JSON.parse(mocks.fetch.mock.calls.find(([,o])=>o?.method==='POST')![1].body);
 expect(first.action).toBe('start');expect(first.request_id).toBe(request);
 expect(JSON.parse(sessionStorage.getItem('wholesaleos.propstream.v1.00000000-0000-4000-8000-000000000001')!)).toEqual(first);
 // The saved-intent alert renders before the request's finally block unlocks
 // retry. Wait for the same readiness an operator needs before clicking.
 const retry=screen.getByRole('button',{name:'Retry exact saved action'});
 await waitFor(()=>expect(retry).toBeEnabled());
 fireEvent.click(retry);
 await waitFor(()=>expect(mocks.fetch.mock.calls.filter(([,o])=>o?.method==='POST')).toHaveLength(2));
 expect(JSON.parse(mocks.fetch.mock.calls.filter(([,o])=>o?.method==='POST')[1][1].body)).toEqual(first);
});
it('recovery clears only a server-confirmed blocked old reference',async()=>{
 const intent={event_id:'00000000-0000-4000-8000-000000000020',request_id:request,lead_id:lead,action:'start',payload:{input_hash:row.input_hash}};
 sessionStorage.setItem('wholesaleos.propstream.v1.00000000-0000-4000-8000-000000000001',JSON.stringify(intent));
 mocks.fetch.mockImplementation(async(url)=>({json:async()=>url.includes('/recover')?{event_id:intent.event_id,settled:true,result:null}:snapshot()}));
 show();fireEvent.click(await screen.findByRole('button',{name:'Recover saved handoff'}));
 await screen.findByText(/old reference is now blocked/);expect(sessionStorage.length).toBe(0);
});
it('new quote stays blocked until explicit evidence review',async()=>{
 mocks.fetch.mockResolvedValue({json:async()=>snapshot([{...row,stage:'quote_and_evidence_required'}])});show();await screen.findByText(/Synthetic verified property/);fireEvent.click(screen.getByText(/Synthetic verified property/));expect(screen.getByRole('button',{name:'Reserve verified quote'})).toBeDisabled();
});
it('non-admin never loads the handoff',()=>{mocks.admin=false;show();expect(mocks.fetch).not.toHaveBeenCalled();});

it('status review is explicit, bound to the viewed signal, and does not start tracing',async()=>{
 mocks.fetch.mockImplementation(async(_url,options)=>({json:async()=>options?.method==='POST'?{...JSON.parse(options.body),operator_id:'00000000-0000-4000-8000-000000000001',outreach_authorized:false}:snapshot([{...row,stage:'current_status_review'}])}));
 show();await screen.findByText(/Synthetic verified property/);fireEvent.click(screen.getByText(/Synthetic verified property/));fireEvent.click(screen.getByText('Review current sale status'));
 const save=screen.getByRole('button',{name:'Save current sale review'});expect(save).toBeDisabled();
 fireEvent.change(screen.getByLabelText('Current sale status evidence URL'),{target:{value:'https://www.dallascounty.org/test'}});
 fireEvent.change(screen.getByLabelText('Current status review notes'),{target:{value:'Synthetic current trustee status verified today'}});
 fireEvent.click(screen.getByLabelText('Sale confirmed active on the reviewed date'));
 fireEvent.click(screen.getByLabelText(/I checked current cancellation/));fireEvent.click(save);
 await screen.findByText(/Current sale review saved/);
 const body=JSON.parse(mocks.fetch.mock.calls.find(([,o])=>o?.method==='POST')![1].body);
 expect(body.action).toBe('review_status');expect(body.payload.signal_hash).toBe(row.signal_hash);expect(body.payload.active).toBe(true);
});
