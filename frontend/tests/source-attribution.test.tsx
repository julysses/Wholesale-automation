import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SourceAttribution } from '../src/components/acquisition/SourceAttribution';
import { ApiError } from '@/lib/api';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), post: vi.fn(), page: {} as Record<string, unknown>, role: 'operator' }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { status = 403; } }));
const w='10000000-0000-4000-8000-000000000001', source='20000000-0000-4000-8000-000000000001', review='30000000-0000-4000-8000-000000000001', campaign='40000000-0000-4000-8000-000000000001', id='50000000-0000-4000-8000-000000000001';
const fingerprint='a'.repeat(64);
const snapshot={id,workspace_id:w,source_id:source,link_review_id:review,campaign_id:campaign,preparation_hash:fingerprint,created_at:'2026-10-26T12:00:00Z',attribution_current:true};
const key=`source-attribution:v1:user:${w}:${source}`;
beforeEach(()=>{
  sessionStorage.clear(); mock.role='operator'; mock.fetch.mockReset(); mock.post.mockReset();
  mock.page={workspace_id:w,source_id:source,preparation_hash:fingerprint,current_link_review_id:review,current_campaign_id:campaign,current_capture:null,items:[],next_after:null,execution_authorized:false};
  mock.post.mockImplementation(async(init:RequestInit)=>{const body=JSON.parse(init.body as string); return {id:body.id,source_id:source,link_review_id:body.link_review_id,campaign_id:campaign,duplicate:false,execution_authorized:false};});
  mock.fetch.mockImplementation(async(path:string,init?:RequestInit)=>({json:async()=>{
    if(init?.method==='POST') return mock.post(init);
    if(path.endsWith('/memberships')) return [{workspace_id:w,user_id:'user',role:mock.role,status:'active'}];
    return {...mock.page};
  }}));
});
function view(onPending=vi.fn()) {return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><SourceAttribution userId="user" workspace={w} intake={source} revision={0} locked={false} onPending={onPending}/></QueryClientProvider>);}
async function ready(){await waitFor(()=>expect(screen.getByRole('button',{name:'Capture current attribution'})).toBeEnabled());}
it('allows an operator to preserve an exact reviewed source without supplying campaign or actor',async()=>{
  view(); await ready(); fireEvent.click(screen.getByRole('button',{name:'Capture current attribution'})); await screen.findByText(/Attribution snapshot recorded/);
  const body=JSON.parse(mock.post.mock.calls[0][0].body); expect(Object.keys(body).sort()).toEqual(['id','link_review_id']); expect(body.link_review_id).toBe(review); expect(sessionStorage.getItem(key)).toBeNull();
});
it('blocks repeated capture even when the current snapshot is on another history page',async()=>{
  mock.page.current_capture=snapshot; view(); await screen.findByText('The current campaign review has a recorded snapshot.'); expect(screen.getByRole('button',{name:'Capture current attribution'})).toBeDisabled();
});
it('does not capture a review that changes during preflight',async()=>{
  view(); await ready(); mock.page.current_link_review_id=id; fireEvent.click(screen.getByRole('button',{name:'Capture current attribution'})); await screen.findByText(/No capture was sent/); expect(mock.post).not.toHaveBeenCalled();
});
it('restores exact pending capture after reload and reconciles a historical reply',async()=>{
  mock.post.mockRejectedValueOnce(new Error('lost')); const pending=vi.fn(); const first=view(pending); await ready();
  fireEvent.click(screen.getByRole('button',{name:'Capture current attribution'})); await screen.findByText(/Capture result unconfirmed/);
  expect(pending).toHaveBeenLastCalledWith(true); const sent=mock.post.mock.calls[0][0].body; first.unmount();
  mock.page.current_link_review_id=null; mock.page.current_campaign_id=null; view();
  fireEvent.click(screen.getByRole('button',{name:'Retry exact attribution capture'})); await screen.findByText(/Attribution snapshot recorded/); expect(mock.post.mock.calls[1][0].body).toBe(sent);
});
it('keeps an earlier uncertain request if its retry is rejected',async()=>{
  mock.post.mockRejectedValueOnce(new Error('lost')).mockRejectedValueOnce(new ApiError('Revoked',403)); view(); await ready();
  fireEvent.click(screen.getByRole('button',{name:'Capture current attribution'})); await screen.findByText(/Capture result unconfirmed/); const saved=sessionStorage.getItem(key);
  fireEvent.click(screen.getByRole('button',{name:'Retry exact attribution capture'})); await waitFor(()=>expect(mock.post).toHaveBeenCalledTimes(2)); expect(sessionStorage.getItem(key)).toBe(saved);
});
it.each([{workspace_id:'other'},{execution_authorized:true},{current_capture:{...snapshot,source_id:id}}])('fails closed on malformed state %j',async patch=>{
  mock.page={...mock.page,...patch}; view(); await screen.findByRole('alert'); expect(screen.getByRole('button',{name:'Capture current attribution'})).toBeDisabled();
});
it('shows revoked captures as historical and denies a new capture without current review',async()=>{
  mock.page={...mock.page,current_link_review_id:null,current_campaign_id:null,items:[{...snapshot,attribution_current:false}]}; view(); await screen.findByText('Historical attribution'); expect(screen.getByRole('button',{name:'Capture current attribution'})).toBeDisabled();
});
it('denies callers and preserves capture on inconsistent success',async()=>{
  mock.role='acquisition_caller'; const first=view(); await screen.findByText(/has not been captured/); expect(screen.getByRole('button',{name:'Capture current attribution'})).toBeDisabled(); first.unmount();
  mock.role='owner'; mock.post.mockImplementation(async(init:RequestInit)=>({...JSON.parse(init.body as string),source_id:source,campaign_id:id,duplicate:false,execution_authorized:false})); view(); await ready(); fireEvent.click(screen.getByRole('button',{name:'Capture current attribution'})); await screen.findByText(/Capture result unconfirmed/); expect(sessionStorage.getItem(key)).not.toBeNull();
});
