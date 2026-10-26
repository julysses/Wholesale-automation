import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CampaignLinkReview } from '../src/components/acquisition/CampaignLinkReview';
import { ApiError } from '@/lib/api';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), post: vi.fn(), role: 'owner', state: {} as Record<string, unknown>, history: [] as unknown[] }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { status = 403; } }));
const w='10000000-0000-4000-8000-000000000001', intake='20000000-0000-4000-8000-000000000001', integration='30000000-0000-4000-8000-000000000001', campaign='40000000-0000-4000-8000-000000000001';
const review={id:'50000000-0000-4000-8000-000000000001',workspace_id:w,integration_id:integration,external_campaign_id:'123',sequence:1,action:'link',campaign_id:campaign,ad_account_id:'999',evidence_ref:'Reviewed ownership file',review_note:'Reviewed Page and account ownership evidence.'};
const storageKey=`campaign-link-review:v1:user:${w}:${intake}`;
beforeEach(() => {
  sessionStorage.clear(); mock.role='owner'; mock.history=[];
  mock.state={workspace_id:w,intake_id:intake,integration_id:integration,page_id:'456',external_campaign_id:'123',preparation_hash:'a'.repeat(64),sequence:0,latest_review:null,link_current:false,internal_campaign_id:null,execution_authorized:false};
  mock.fetch.mockReset(); mock.post.mockReset();
  mock.post.mockImplementation(async(init:RequestInit)=>{const body=JSON.parse(init.body as string);return {review_id:body.id,sequence:body.expected_sequence+1,duplicate:false,execution_authorized:false};});
  mock.fetch.mockImplementation(async(path:string,init?:RequestInit)=>({json:async()=>{
    if(init?.method==='POST') return mock.post(init);
    if(path.endsWith('/campaign-link-state')) return {...mock.state};
    if(path.includes('/campaign-link-reviews?')) return mock.history;
    if(path.endsWith('/memberships')) return [{workspace_id:w,user_id:'user',role:mock.role,status:'active'}];
    return {items:[{id:campaign,workspace_id:w,name:'Dallas campaign',acquisition_channel:'facebook'}],next_after:null};
  }}));
});
function view(onPending=vi.fn()) {return render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><CampaignLinkReview userId="user" workspace={w} intake={intake} locked={false} onPending={onPending}/></QueryClientProvider>);}
async function fill(action='link') {
  await waitFor(()=>expect(screen.getByLabelText('Campaign decision')).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Campaign decision'),{target:{value:action}});
  if(action==='link') { fireEvent.change(screen.getByLabelText('Workspace Facebook campaign'),{target:{value:campaign}}); fireEvent.change(screen.getByLabelText('Reviewed advertising account ID'),{target:{value:'999'}}); }
  fireEvent.change(screen.getByLabelText('Campaign ownership evidence reference'),{target:{value:'Reviewed ownership file'}});
  fireEvent.change(screen.getByLabelText('Campaign review note'),{target:{value:'Reviewed Page and account ownership evidence.'}});
  fireEvent.click(screen.getByRole('checkbox'));
}
it('rechecks evidence and submits the reviewed ad account separately from the Page',async()=>{
  view(); await fill(); expect(screen.getByText('Facebook Page: 456')).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'Record campaign review'})); await screen.findByText(/Campaign review recorded/);
  const body=JSON.parse(mock.post.mock.calls[0][0].body); expect(body.ad_account_id).toBe('999'); expect(body.campaign_id).toBe(campaign); expect(body.expected_sequence).toBe(0); expect(body.actor_id).toBeUndefined(); expect(body.integration_id).toBeUndefined();
  expect(mock.fetch.mock.calls.filter(call=>call[0].endsWith('/campaign-link-state')).length).toBeGreaterThanOrEqual(2); expect(sessionStorage.getItem(storageKey)).toBeNull();
});
it('requires acknowledgment and rejects stale evidence before any write',async()=>{
  view(); await fill(); fireEvent.click(screen.getByRole('checkbox')); expect(screen.getByRole('button',{name:'Record campaign review'})).toBeDisabled(); fireEvent.click(screen.getByRole('checkbox'));
  mock.state.preparation_hash='b'.repeat(64); fireEvent.click(screen.getByRole('button',{name:'Record campaign review'}));
  await screen.findByText(/No review was sent/); expect(mock.post).not.toHaveBeenCalled();
});
it('retains an uncertain request through refresh and reload, then reconciles exactly',async()=>{
  const pending=vi.fn(); mock.post.mockRejectedValueOnce(new Error('lost')); const original=view(pending); await fill();
  fireEvent.click(screen.getByRole('button',{name:'Record campaign review'})); await screen.findByText(/Result unconfirmed/);
  expect(pending).toHaveBeenLastCalledWith(true); const body=mock.post.mock.calls[0][0].body; expect(sessionStorage.getItem(storageKey)).toBe(body);
  fireEvent.click(screen.getByRole('button',{name:'Refresh campaign evidence'})); expect(screen.getByLabelText('Campaign review note')).toBeDisabled(); original.unmount();
  view(); fireEvent.click(screen.getByRole('button',{name:'Retry exact campaign review'})); await screen.findByText(/Campaign review recorded/);
  expect(mock.post.mock.calls[1][0].body).toBe(body);
});
it('does not discard an uncertain original after a rejected retry',async()=>{
  mock.post.mockRejectedValueOnce(new Error('lost')).mockRejectedValueOnce(new ApiError('Denied',403)); view(); await fill();
  fireEvent.click(screen.getByRole('button',{name:'Record campaign review'})); await screen.findByText(/Result unconfirmed/); const body=sessionStorage.getItem(storageKey);
  fireEvent.click(screen.getByRole('button',{name:'Retry exact campaign review'})); await waitFor(()=>expect(mock.post).toHaveBeenCalledTimes(2)); expect(sessionStorage.getItem(storageKey)).toBe(body); expect(screen.getByLabelText('Campaign review note')).toBeDisabled();
});
it('permits reviewed revocation of a stale link but blocks replacement first',async()=>{
  mock.state={...mock.state,sequence:1,latest_review:review}; mock.history=[review]; view(); await fill();
  expect(screen.getByRole('button',{name:'Record campaign review'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Campaign decision'),{target:{value:'revoke'}}); fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button',{name:'Record campaign review'})); await screen.findByText(/Campaign review recorded/);
  const body=JSON.parse(mock.post.mock.calls[0][0].body); expect(body.action).toBe('revoke'); expect(body.campaign_id).toBeNull(); expect(body.ad_account_id).toBeNull();
});
it('keeps operator access read-only',async()=>{
  mock.role='operator'; view(); await screen.findByText('Facebook Page: 456'); expect(screen.getByRole('button',{name:'Record campaign review'})).toBeDisabled(); expect(screen.getByLabelText('Campaign decision')).toBeDisabled();
});
it.each([{workspace_id:'other'},{execution_authorized:true},{link_current:true},{external_campaign_id:123}])('rejects inconsistent state %j',async patch=>{
  mock.state={...mock.state,...patch}; view(); await screen.findByText(/Campaign evidence unavailable/); expect(screen.getByRole('button',{name:'Record campaign review'})).toBeDisabled();
});
it('rejects foreign-workspace history before permitting a review',async()=>{
  mock.history=[{...review,workspace_id:'other'}]; view(); await screen.findByText('Campaign history unavailable.'); expect(screen.getByRole('button',{name:'Record campaign review'})).toBeDisabled();
});
it('rejects an authorized execution response and preserves the same request',async()=>{
  mock.post.mockImplementation(async(init:RequestInit)=>{const body=JSON.parse(init.body as string);return {review_id:body.id,sequence:1,duplicate:false,execution_authorized:true};});
  view(); await fill(); fireEvent.click(screen.getByRole('button',{name:'Record campaign review'})); await screen.findByText(/Result unconfirmed/); expect(sessionStorage.getItem(storageKey)).not.toBeNull();
});
it('locks campaign decisions while a source capture is being reconciled',async()=>{
  const key=`source-attribution:v1:user:${w}:${intake}`;
  sessionStorage.setItem(key,JSON.stringify({id:'50000000-0000-4000-8000-000000000001',link_review_id:'60000000-0000-4000-8000-000000000001',campaign_id:campaign,preparation_hash:'a'.repeat(64)}));
  const pending=vi.fn(); view(pending);
  await waitFor(()=>expect(pending).toHaveBeenLastCalledWith(true));
  expect(screen.getByLabelText('Campaign decision')).toBeDisabled();
  expect(screen.getByRole('button',{name:'Retry exact attribution capture'})).toBeEnabled();
});
