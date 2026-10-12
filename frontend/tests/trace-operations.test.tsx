import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {QueryClient,QueryClientProvider} from '@tanstack/react-query';
import {beforeEach,expect,it,vi} from 'vitest';
const actor='00000000-0000-4000-8000-000000000001',trace='00000000-0000-4000-8000-000000000002';
const mocks=vi.hoisted(()=>({fetch:vi.fn(),admin:true}));
vi.mock('@/lib/api',async original=>({...await original<typeof import('@/lib/api')>(),apiFetch:mocks.fetch}));
vi.mock('@/hooks/useProfile',()=>({useProfile:()=>({isAdmin:mocks.admin,profile:{id:actor}})}));
import {TraceOperations} from '@/components/lists/TraceOperations';
const snapshot={day:'2026-10-12',budget:{cap_cents:100,reserved_cents:60,actual_cents:0},total_held_cents:60,open_count:1,requests:[{id:trace,lead_id:actor,provider:'synthetic',spend_day:'2026-10-12',reserved_cents:60,state:'reserved',created_at:'2026-10-12T00:00:00Z'}],recent_actions:[]};
const mount=()=>render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><TraceOperations/></QueryClientProvider>);
beforeEach(()=>{sessionStorage.clear();vi.resetAllMocks();mocks.admin=true;mocks.fetch.mockResolvedValue({json:async()=>snapshot});});
it('shows held money and never offers cancellation for uncertain provider submissions',async()=>{
 mocks.fetch.mockResolvedValue({json:async()=>({...snapshot,requests:[{...snapshot.requests[0],state:'unknown'}]})});
 mount();await screen.findByText(/1 unresolved requests/);
 expect(screen.getByText(/Reserved across all days: \$0.60/)).toBeTruthy();
 expect(screen.queryByRole('button',{name:'Cancel unsubmitted reservation'})).toBeNull();
});
it('recovers the same event identity after lost acknowledgement and remount',async()=>{
 let attempt=0;const ids:string[]=[];
 mocks.fetch.mockImplementation(async(_path:string,init?:RequestInit)=>{
  if(!init)return {json:async()=>snapshot};
  const {event_id}=JSON.parse(init.body as string);ids.push(event_id);
  if(attempt++===0)throw new Error('Connection lost');
  return {json:async()=>({event:{id:event_id,operator_id:actor,request_id:trace,action:'cancel_reserved',result:{request:{id:trace,state:'failed',actual_cents:0,provider_job_id:'not_submitted'}}}})};
 });
 const first=mount();fireEvent.click(await screen.findByRole('button',{name:'Cancel unsubmitted reservation'}));
 await screen.findByText('Connection lost');first.unmount();mount();
 fireEvent.click(await screen.findByRole('button',{name:'Retry saved cancellation'}));
 await screen.findByRole('status');expect(ids).toHaveLength(2);expect(ids[0]).toBe(ids[1]);
 expect(sessionStorage.getItem(`hilltop.trace-cancel.v1.${actor}`)).toBeNull();
});
it('does not fetch operator records for non-admins',async()=>{
 mocks.admin=false;mount();await waitFor(()=>expect(mocks.fetch).not.toHaveBeenCalled());
});
it('keeps uncertain identity if a response belongs to another cancellation',async()=>{
 mocks.fetch.mockImplementation(async(_path:string,init?:RequestInit)=>init?{json:async()=>({event:{}})}:{json:async()=>snapshot});
 mount();fireEvent.click(await screen.findByRole('button',{name:'Cancel unsubmitted reservation'}));
 await screen.findByRole('button',{name:'Retry saved cancellation'});
 expect(sessionStorage.getItem(`hilltop.trace-cancel.v1.${actor}`)).not.toBeNull();
 expect(screen.queryByRole('status')).toBeNull();
});
