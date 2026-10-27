import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InboundRequests } from '../src/components/acquisition/InboundRequests';
const mock = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch }));
const w = '10000000-0000-4000-8000-000000000001', integration = '96000000-0000-4000-8000-000000000001';
const row = { id: '98000000-0000-4000-8000-000000000001', acquisition_revision: 2, acquisition_request_kind: 'request_callback', acquisition_evidence: {phone:'2145550101',preferred_time:'Tomorrow afternoon',purpose:'Discuss repairs',requested_by_caller:true}, acquisition_phone:'+12145550101',acquisition_request_hash:'a'.repeat(64),created_at:'2026-10-26T18:00:00Z' };
const page = {workspace_id:w,integration_id:integration,call_id:'call_test',items:[row],execution_authorized:false};
beforeEach(() => { mock.fetch.mockReset(); mock.fetch.mockResolvedValue({json:async()=>page}); });
function view() {render(<QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}><InboundRequests userId="user" workspace={w} contextId="intake" integration={integration} call="call_test" /></QueryClientProvider>);}
async function open(){view(); expect(mock.fetch).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole('button',{name:'View inbound requests'}));}
it('reads only on demand and labels callback evidence without scheduling or execution', async()=>{
  await open(); await screen.findByText('Callback requested · revision 2');
  expect(screen.getByText(/not verified/)).toBeVisible(); expect(screen.getByText(/Tomorrow afternoon — not scheduled/)).toBeVisible();
  expect(mock.fetch.mock.calls[0][0]).toBe(`/api/acquisition/workspaces/${w}/inbound/integrations/${integration}/calls/call_test/requests?limit=20`);
  expect(mock.fetch.mock.calls.every(([,init])=>!init.method)).toBe(true);
});
it('shows assistant escalation without claiming a transfer', async()=>{
  mock.fetch.mockResolvedValue({json:async()=>({...page,items:[{...row,acquisition_request_kind:'request_human',acquisition_phone:null,acquisition_evidence:{reason:'unsupported_language',details:'Caller needs language support',requested_by_caller:false}}]})});
  await open(); await screen.findByText('Human assistance requested · revision 2'); expect(screen.getByText('Raised by intake assistant')).toBeVisible();
});
it.each([
  {...page,workspace_id:'another'}, {...page,integration_id:'another'}, {...page,call_id:'another'}, {...page,execution_authorized:true},
  {...page,items:[{...row,acquisition_evidence:{...row.acquisition_evidence,requested_by_caller:false}}]},
  {...page,items:[{...row,acquisition_revision:0}]}, {...page,items:[row,row]},
  {...page,items:[{...row,acquisition_request_kind:'send_call'}]},
])('rejects mismatched or malformed responses',async(value)=>{
  mock.fetch.mockResolvedValue({json:async()=>value}); await open(); await screen.findByRole('alert'); expect(screen.queryByText(/Callback requested ·/)).not.toBeInTheDocument();
});
it('clears previously shown request evidence on denied refresh',async()=>{
  await open(); await screen.findByText('Callback requested · revision 2'); mock.fetch.mockRejectedValue(new Error('Denied'));
  fireEvent.click(screen.getByRole('button',{name:'Refresh inbound requests'})); await screen.findByRole('alert'); expect(screen.queryByText(/Tomorrow afternoon/)).not.toBeInTheDocument();
});
it('uses a bounded UUID cursor and labels the empty terminal page honestly',async()=>{
  const items=Array.from({length:20},(_,i)=>({...row,id:`98000000-0000-4000-8000-${String(i+1).padStart(12,'0')}`}));
  mock.fetch.mockResolvedValueOnce({json:async()=>({...page,items})}).mockResolvedValueOnce({json:async()=>({...page,items:[]})});
  await open(); await screen.findAllByText('Callback requested · revision 2'); fireEvent.click(screen.getByRole('button',{name:'More requests'}));
  await screen.findByText('No saved requests on this page.'); expect(mock.fetch.mock.calls[1][0]).toContain('&after='+items[19].id);
  expect(screen.getByRole('button',{name:'More requests'})).toBeDisabled(); expect(screen.getByRole('button',{name:'Previous requests'})).toBeEnabled();
});
