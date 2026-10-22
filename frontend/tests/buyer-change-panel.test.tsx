import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
const state=vi.hoisted(()=>({recover:vi.fn(),pending:vi.fn()}));
vi.mock('@/lib/buyerChanges',()=>({BUYER_CHANGE_EVENT:'test-buyer-change',buyerChangeMessage:(s:string)=>s==='deleted'?'Buyer deletion confirmed.':'No saved result is confirmed yet.',pendingBuyerChange:state.pending,recoverBuyerChange:state.recover}));
import { BuyerChangeRecovery } from '@/components/buyers/BuyerChangeRecovery';
function mount(){const client=new QueryClient({defaultOptions:{queries:{retry:false}}});render(<QueryClientProvider client={client}><BuyerChangeRecovery /></QueryClientProvider>);return client;}
beforeEach(()=>{
 vi.clearAllMocks();state.pending.mockResolvedValue({request_id:'saved-reference',kind:'delete',expected:{first_name:'Synthetic',last_name:'Buyer'}});
});
it('does no write on mount; a pending read cannot release the original deletion',async()=>{
 mount();await screen.findByText(/Unconfirmed deletion/);expect(state.recover).not.toHaveBeenCalled();
 state.recover.mockResolvedValueOnce({state:'pending'});fireEvent.click(screen.getByText('Check buyer change'));
 await screen.findByRole('status');expect(state.recover).toHaveBeenCalledWith('check');
 expect(screen.getByText('Retry original buyer change')).toBeEnabled();
 expect(screen.getByText(/saved-reference/)).toBeInTheDocument();
});
it('retains a failed stop and only releases the pending UI after a terminal receipt',async()=>{
 const client=mount();const refresh=vi.spyOn(client,'invalidateQueries');await screen.findByText(/Unconfirmed deletion/);
 state.recover.mockRejectedValueOnce(new Error('Synthetic unconfirmed stop'));fireEvent.click(screen.getByText('Stop pending buyer change'));
 await screen.findByText('Synthetic unconfirmed stop');expect(screen.getByText('Retry original buyer change')).toBeEnabled();
 expect(refresh).not.toHaveBeenCalled();state.recover.mockResolvedValueOnce({state:'deleted'});
 fireEvent.click(screen.getByText('Check buyer change'));
 await waitFor(()=>expect(screen.queryByText('Retry original buyer change')).not.toBeInTheDocument());
 expect(screen.getByRole('status')).toHaveTextContent('deletion confirmed');expect(refresh).toHaveBeenCalled();
});
