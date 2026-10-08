import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ api: vi.fn(), success: vi.fn(), error: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.api }));
vi.mock('sonner', () => ({ toast: { success: mocks.success, error: mocks.error } }));
vi.mock('@/hooks/useLeads', () => ({ useLeads: () => ({ data: { data: [{ id: 'lead-1', property_address: 'Test Property' }] } }) }));
import { DealAnalyzer } from '@/pages/DealAnalyzer';
function mount(){render(<QueryClientProvider client={new QueryClient()}><DealAnalyzer /></QueryClientProvider>);}
beforeEach(() => {
 vi.clearAllMocks();sessionStorage.clear();
 mocks.api.mockImplementation(async (_path, init) => {const b=JSON.parse(init.body);return {json:async()=>({analysis:{id:b.request_id,lead_id:b.lead_id}})};});
 mount();fireEvent.change(screen.getByLabelText('ARV Override'), {target:{value:'250000'}});
 fireEvent.change(screen.getByLabelText('Select Lead'), {target:{value:'lead-1'}});
});
it('saves one manifest and requires deliberate new analysis after success',async()=>{
 const save=screen.getByRole('button',{name:/Save ARV/});fireEvent.click(save);fireEvent.click(save);
 await waitFor(()=>expect(mocks.success).toHaveBeenCalled());expect(mocks.api).toHaveBeenCalledTimes(1);
 expect(JSON.parse(mocks.api.mock.calls[0][1].body).inputs).toMatchObject({arv:250000,repairs:37500,assignment_fee:15000});
 expect(save).toBeDisabled();expect(screen.getByRole('button',{name:'Start a new analysis'})).toBeEnabled();expect(sessionStorage.length).toBe(0);
});
it('recovers uncertain reference across reload and retries identical inputs',async()=>{
 mocks.api.mockRejectedValueOnce(new Error('Acknowledgement lost'));
 fireEvent.click(screen.getByRole('button',{name:/Save ARV/}));
 await waitFor(()=>expect(screen.getByRole('button',{name:'Retry same analysis save'})).toBeEnabled());
 const first=mocks.api.mock.calls[0][1].body;expect(screen.getByLabelText('ARV Override')).toBeDisabled();
 cleanup();mount();await waitFor(()=>expect(screen.getByRole('button',{name:'Retry same analysis save'})).toBeEnabled());
 fireEvent.click(screen.getByRole('button',{name:'Retry same analysis save'}));await waitFor(()=>expect(mocks.success).toHaveBeenCalled());
 expect(mocks.api.mock.calls[1][1].body).toBe(first);
});
it('reports AI failure without inventing a recommendation',async()=>{
 mocks.api.mockRejectedValue(new Error('AI is unavailable'));fireEvent.click(screen.getByRole('button',{name:'Get AI Take'}));
 await waitFor(()=>expect(mocks.error).toHaveBeenCalledWith('AI is unavailable'));
 expect(screen.queryByText(/Your numbers look solid/)).not.toBeInTheDocument();
});
