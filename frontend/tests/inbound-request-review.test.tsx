import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InboundRequestReview } from '../src/components/acquisition/InboundRequestReview';
const mock=vi.hoisted(()=>({fetch:vi.fn(),post:vi.fn(),state:undefined as unknown,role:'operator'}));
vi.mock('@/lib/api',()=>({apiFetch:mock.fetch,ApiError:class extends Error{status=409;}}));
const w='10000000-0000-4000-8000-000000000001',u='00000000-0000-4000-8000-000000000001',t='98000000-0000-4000-8000-000000000001',other='00000000-0000-4000-8000-000000000002';
const key=`inbound-request-review:v1:${u}:${w}:${t}`;
const base={workspace_id:w,task_id:t,sequence:0,request_hash:'a'.repeat(64),latest_review:null,request_current:true,review_current:false,status:'pending_review',assigned_user_id:null,execution_authorized:false,contact_permission_granted:false,checked_at:'2026-10-26T20:00:00Z'};
const decision={id:'a1000000-0000-4000-8000-000000000001',expected_sequence:0,request_hash:'a'.repeat(64),status:'assigned',assigned_user_id:u,review_note:'Reviewed the request and assigned accountable follow-up.'};
beforeEach(()=>{sessionStorage.clear();mock.fetch.mockReset();mock.post.mockReset();mock.role='operator';mock.state={...base};
 mock.post.mockImplementation(async(body)=>({review_id:body.id,sequence:body.expected_sequence+1,duplicate:false,execution_authorized:false}));
 mock.fetch.mockImplementation(async(path:string,init?:RequestInit)=>({json:async()=>{
  if(init?.method==='POST')return mock.post(JSON.parse(String(init.body)));
  if(path.endsWith('/state'))return mock.state;
  if(path.endsWith('/memberships'))return [{workspace_id:w,user_id:u,role:mock.role,status:'active'},{workspace_id:w,user_id:other,role:'operator',status:'active'}];
  if(path.includes('/reviews?'))return [];
  throw new Error('Unknown path');
 }}));
});
function view(){return render(<QueryClientProvider client={new QueryClient()}><InboundRequestReview userId={u} workspace={w} task={t} onPending={()=>{}} onClose={()=>{}}/></QueryClientProvider>);}
async function fill(){await screen.findByText('Current status: pending review');await waitFor(()=>expect(screen.getByLabelText('Review note')).toBeEnabled());fireEvent.change(screen.getByLabelText('Review note'),{target:{value:decision.review_note}});fireEvent.click(screen.getByRole('checkbox'));}
it('requires acknowledgement and records a scoped review without execution',async()=>{view();await fill();fireEvent.click(screen.getByRole('button',{name:'Save request review'}));await screen.findByText(/Review decision recorded/);expect(mock.post).toHaveBeenCalledTimes(1);expect(mock.post.mock.calls[0][0]).toMatchObject({...decision,id:expect.any(String)});expect(sessionStorage.getItem(key)).toBeNull();});
it('freezes unknown outcomes and retries the identical request after remount',async()=>{mock.post.mockRejectedValueOnce(new Error('lost reply'));const result=view();await fill();fireEvent.click(screen.getByRole('button',{name:'Save request review'}));await screen.findByRole('button',{name:'Retry exact request review'});const original=JSON.parse(sessionStorage.getItem(key)!);expect(screen.getByLabelText('Review note')).toBeDisabled();expect(screen.getByRole('button',{name:'Close request review'})).toBeDisabled();result.unmount();view();fireEvent.click(await screen.findByRole('button',{name:'Retry exact request review'}));await screen.findByText(/Review decision recorded/);expect(mock.post.mock.calls[1][0]).toEqual(original);expect(sessionStorage.getItem(key)).toBeNull();});
it('retains a previously unknown request when retry is rejected',async()=>{sessionStorage.setItem(key,JSON.stringify(decision));const {ApiError}=await import('@/lib/api');mock.post.mockRejectedValue(new ApiError('Conflict'));view();fireEvent.click(screen.getByRole('button',{name:'Retry exact request review'}));await screen.findByText(/Result unconfirmed/);expect(JSON.parse(sessionStorage.getItem(key)!)).toEqual(decision);expect(screen.getByRole('button',{name:'Close request review'})).toBeDisabled();});
it('clears a fresh definitely rejected request',async()=>{const {ApiError}=await import('@/lib/api');mock.post.mockRejectedValue(new ApiError('Conflict'));view();await fill();fireEvent.click(screen.getByRole('button',{name:'Save request review'}));await screen.findByText(/Review was not recorded/);expect(sessionStorage.getItem(key)).toBeNull();});
it('blocks stale evidence before creating a request',async()=>{view();await fill();mock.state={...base,request_current:false,status:'superseded'};fireEvent.click(screen.getByRole('button',{name:'Save request review'}));await screen.findByText(/Review was not recorded/);expect(mock.post).not.toHaveBeenCalled();expect(sessionStorage.getItem(key)).toBeNull();});
it('requires an assignment before completing a review',async()=>{view();await fill();fireEvent.change(screen.getByLabelText('Review action'),{target:{value:'review_complete'}});fireEvent.click(screen.getByRole('checkbox'));expect(screen.getByRole('button',{name:'Save request review'})).toBeDisabled();});
it('does not offer other assignees to operators',async()=>{view();await fill();expect(screen.queryByRole('option',{name:`${other} (operator)`})).not.toBeInTheDocument();});
it('offers eligible assignees to administrators',async()=>{mock.role='admin';view();await fill();expect(screen.getByRole('option',{name:`${other} (operator)`})).toBeInTheDocument();});
it.each([{...base,workspace_id:'wrong'},{...base,execution_authorized:true},{...base,status:'review_complete'},{...base,sequence:1}])('rejects malformed or inconsistent current state',async(value)=>{mock.state=value;view();await screen.findByText('Current review unavailable. Refresh and verify access.');expect(screen.getByRole('button',{name:'Save request review'})).toBeDisabled();});
it('blocks malformed stored pending requests without overwriting them',async()=>{sessionStorage.setItem(key,'broken');view();await screen.findByText(/Pending review could not be recovered/);expect(screen.getByRole('button',{name:'Save request review'})).toBeDisabled();expect(sessionStorage.getItem(key)).toBe('broken');});
it('treats an execution-authorized receipt as unconfirmed',async()=>{mock.post.mockImplementation(async(body)=>({review_id:body.id,sequence:1,duplicate:false,execution_authorized:true}));view();await fill();fireEvent.click(screen.getByRole('button',{name:'Save request review'}));await screen.findByText(/Result unconfirmed/);expect(sessionStorage.getItem(key)).not.toBeNull();});

it('completes an assigned request with the current sequence and keeps contact separate',async()=>{
 const latest={id:decision.id,workspace_id:w,task_id:t,sequence:1,request_hash:base.request_hash,status:'assigned',assigned_user_id:u,review_note:decision.review_note,actor_id:u,created_at:base.checked_at};
 mock.state={...base,sequence:1,latest_review:latest,status:'assigned',assigned_user_id:u,review_current:true};
 view();await screen.findByText('Current status: assigned');await waitFor(()=>expect(screen.getByLabelText('Review note')).toBeEnabled());
 fireEvent.change(screen.getByLabelText('Review action'),{target:{value:'review_complete'}});fireEvent.change(screen.getByLabelText('Review note'),{target:{value:'Reviewed all request evidence. No contact was executed.'}});fireEvent.click(screen.getByRole('checkbox'));
 fireEvent.click(screen.getByRole('button',{name:'Save request review'}));await screen.findByText(/Review decision recorded/);
 expect(mock.post.mock.calls[0][0]).toMatchObject({expected_sequence:1,status:'review_complete',assigned_user_id:u});
});
it('does not send when durable pending storage fails',async()=>{
 view();await fill();const storage=vi.spyOn(Storage.prototype,'setItem').mockImplementation(()=>{throw new Error('Storage unavailable');});
 try{fireEvent.click(screen.getByRole('button',{name:'Save request review'}));await screen.findByText(/Review was not recorded/);expect(mock.post).not.toHaveBeenCalled();}finally{storage.mockRestore();}
});
