import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { InboundRequestQueue } from '../src/components/acquisition/InboundRequestQueue';
const mock = vi.hoisted(()=>({fetch:vi.fn()}));
vi.mock('@/lib/api',()=>({apiFetch:mock.fetch}));
const w='10000000-0000-4000-8000-000000000001';
const row={id:'98000000-0000-4000-8000-000000000001',integration_id:'96000000-0000-4000-8000-000000000001',call_id:'call_no_intake',request_kind:'request_callback',revision:2,created_at:'2026-10-26T18:00:00Z'};
const page={workspace_id:w,items:[row],next_after:null,checked_at:'2026-10-26T19:00:00Z',revision_scope:'latest_per_call_and_kind_at_read',review_status_available:false,execution_authorized:false};
beforeEach(()=>{mock.fetch.mockReset();mock.fetch.mockResolvedValue({json:async()=>page});});
function view(){render(<QueryClientProvider client={new QueryClient()}><InboundRequestQueue userId="user" workspace={w}/></QueryClientProvider>);}
async function open(){view();expect(mock.fetch).not.toHaveBeenCalled();fireEvent.click(screen.getByRole('button',{name:'Inbound callback and assistance requests'}));}
it('discovers a call without an intake and opens its independently scoped history',async()=>{
 await open();await screen.findByText('Callback requested · revision 2');expect(screen.getByText(/Includes calls without a completed intake/)).toBeVisible();
 mock.fetch.mockResolvedValue({json:async()=>({workspace_id:w,integration_id:row.integration_id,call_id:row.call_id,items:[],execution_authorized:false})});
 fireEvent.click(screen.getByRole('button',{name:'View call request history'}));await screen.findByText('No saved requests on this page.');
 expect(mock.fetch.mock.calls[1][0]).toContain(`/integrations/${row.integration_id}/calls/call_no_intake/requests`);
});
it.each([{...page,workspace_id:'wrong'},{...page,execution_authorized:true},{...page,review_status_available:true},{...page,next_after:row.id},{...page,items:[row,row]},{...page,items:[{...row,revision:0}]}])('rejects inconsistent queue data',async data=>{
 mock.fetch.mockResolvedValue({json:async()=>data});await open();await screen.findByRole('alert');expect(screen.queryByRole('button',{name:'View call request history'})).not.toBeInTheDocument();
});
it('clears selected call history when queue refresh denies access',async()=>{
 await open();await screen.findByText('Callback requested · revision 2');fireEvent.click(screen.getByRole('button',{name:'View call request history'}));
 mock.fetch.mockRejectedValue(new Error('Denied'));fireEvent.click(screen.getByRole('button',{name:'Refresh request queue'}));await screen.findByRole('alert');
 expect(screen.queryByText('Call: call_no_intake')).not.toBeInTheDocument();expect(screen.queryByRole('button',{name:'View inbound requests'})).not.toBeInTheDocument();
});
it('follows bounded cursors and refreshes back to the first page',async()=>{
 const items=Array.from({length:20},(_,i)=>({...row,id:`98000000-0000-4000-8000-${String(i+1).padStart(12,'0')}`,call_id:`call_${i}`}));
 mock.fetch.mockResolvedValueOnce({json:async()=>({...page,items,next_after:items[19].id})}).mockResolvedValueOnce({json:async()=>({...page,items:[]})}).mockResolvedValue({json:async()=>page});
 await open();await screen.findAllByText('Callback requested · revision 2');fireEvent.click(screen.getByRole('button',{name:'More request pages'}));await screen.findByText('No requests on this page.');
 expect(mock.fetch.mock.calls[1][0]).toContain('&after='+items[19].id);fireEvent.click(screen.getByRole('button',{name:'Refresh request queue'}));await screen.findByText('Callback requested · revision 2');expect(mock.fetch.mock.calls.at(-1)?.[0]).not.toContain('after=');
});
