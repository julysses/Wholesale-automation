import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import type { Deal, Lead } from '@/types';
import { useDealStore } from '@/stores/useDealStore';
import { localDateString } from '@/lib/taskDates';

type Drop = { active: { id: string }; over: { id: string } | null };
const mocks = vi.hoisted(() => ({
  create: vi.fn(), update: vi.fn(), refetch: vi.fn(), leads: vi.fn(),
  error: null as Error | null,
  dragEnd: undefined as ((event: Drop) => Promise<void>) | undefined,
}));
const deals = [
  { id: 'deal-1', lead_id: 'lead-1', deal_name: '123 Main St', stage: 'offer_made', closing_date: '2026-09-15' },
  { id: 'deal-2', lead_id: 'lead-2', deal_name: '456 Oak St', stage: 'closed', actual_close_date: '2026-09-01' },
] as Deal[];
const leads = [{ id: 'lead-1', property_address: '123 Main St', city: 'Dallas', mao: 125000 }] as Lead[];

vi.mock('@/hooks/useDeals', () => ({
  useDeals: () => ({ data: deals, isLoading: false, error: mocks.error, refetch: mocks.refetch }),
  useCreateDeal: () => ({ mutateAsync: mocks.create, isPending: false }),
  useUpdateDeal: () => ({ mutateAsync: mocks.update, isPending: false }),
}));
vi.mock('@/hooks/useLeads', () => ({ useLeads: (filters: unknown) => mocks.leads(filters) }));
vi.mock('@dnd-kit/core', () => ({
  DndContext: ({ children, onDragEnd }: { children: ReactNode; onDragEnd: (event: Drop) => Promise<void> }) => { mocks.dragEnd = onDragEnd; return children; },
  DragOverlay: ({ children }: { children: ReactNode }) => children,
  useSensor: vi.fn(), useSensors: vi.fn(), PointerSensor: vi.fn(), closestCorners: vi.fn(),
}));
vi.mock('@/components/pipeline/KanbanColumn', () => ({
  KanbanColumn: ({ title, deals: rows, onDealClick }: { title: string; deals: Deal[]; onDealClick: (deal: Deal) => void }) => (
    <section aria-label={title}>{rows.map((deal) => <button key={deal.id} onClick={() => onDealClick(deal)}>{deal.deal_name}</button>)}</section>
  ),
}));
import { Pipeline } from '@/pages/Pipeline';

beforeEach(() => {
  vi.clearAllMocks();
  mocks.error = null;
  mocks.create.mockResolvedValue({});
  mocks.update.mockResolvedValue({});
  mocks.leads.mockReturnValue({ data: { data: leads, count: 1 }, isLoading: false });
  useDealStore.setState({ deals });
});

it('requires a linked lead and prefills a new deal from that lead', async () => {
  render(<Pipeline />);
  fireEvent.click(screen.getByRole('button', { name: 'New Deal', exact: true }));
  fireEvent.change(screen.getByLabelText('Deal Name / Property Address'), { target: { value: 'Manual address' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create Deal' }));
  expect(mocks.create).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Lead *'), { target: { value: 'lead-1' } });
  expect(screen.getByLabelText('Deal Name / Property Address')).toHaveValue('123 Main St');
  fireEvent.click(screen.getByRole('button', { name: 'Create Deal' }));
  await waitFor(() => expect(mocks.create).toHaveBeenCalledWith(expect.objectContaining({ lead_id: 'lead-1', deal_name: '123 Main St', contract_price: 125000 })));
});

it('allows searching and paging lead selection beyond the initial 50 rows', () => {
  mocks.leads.mockReturnValue({ data: { data: leads, count: 120 }, isLoading: false });
  render(<Pipeline />);
  fireEvent.click(screen.getByRole('button', { name: 'New Deal', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Next leads' }));
  expect(mocks.leads).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }));
  fireEvent.change(screen.getByLabelText('Find Lead'), { target: { value: 'Oak' } });
  expect(mocks.leads).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, search: 'Oak' }));
});

it('moves a deal onto another card and records its closing date', async () => {
  render(<Pipeline />);
  await act(async () => { await mocks.dragEnd?.({ active: { id: 'deal-1' }, over: { id: 'deal-2' } }); });
  expect(mocks.update).toHaveBeenCalledWith({ id: 'deal-1', updates: { stage: 'closed', actual_close_date: localDateString() } });
  expect(useDealStore.getState().deals.find((deal) => deal.id === 'deal-1')?.stage).toBe('closed');
});

it('rolls back a rejected stage move', async () => {
  mocks.update.mockRejectedValueOnce(new Error('Write denied'));
  render(<Pipeline />);
  await act(async () => { await mocks.dragEnd?.({ active: { id: 'deal-1' }, over: { id: 'under_contract' } }); });
  expect(useDealStore.getState().deals.find((deal) => deal.id === 'deal-1')?.stage).toBe('offer_made');
});

it('clears actual closing date when reopening a closed deal', async () => {
  render(<Pipeline />);
  await act(async () => { await mocks.dragEnd?.({ active: { id: 'deal-2' }, over: { id: 'offer_made' } }); });
  expect(mocks.update).toHaveBeenCalledWith({ id: 'deal-2', updates: { stage: 'offer_made', actual_close_date: null } });
});

it('sends null when a deal date is cleared and retains failed saves for retry', async () => {
  mocks.update.mockRejectedValueOnce(new Error('Write denied'));
  render(<Pipeline />);
  fireEvent.click(screen.getByRole('button', { name: '123 Main St' }));
  fireEvent.change(screen.getByLabelText('Closing Date'), { target: { value: '' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
  await waitFor(() => expect(mocks.update).toHaveBeenCalled());
  expect(mocks.update.mock.calls[0][0].updates.closing_date).toBeNull();
  expect(screen.getByLabelText('Closing Date')).toHaveValue('');
  fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
  await waitFor(() => expect(screen.queryByLabelText('Closing Date')).not.toBeInTheDocument());
});

it('keeps a failed new deal draft open for retry', async () => {
  mocks.create.mockRejectedValueOnce(new Error('Write denied'));
  render(<Pipeline />);
  fireEvent.click(screen.getByRole('button', { name: 'New Deal', exact: true }));
  fireEvent.change(screen.getByLabelText('Lead *'), { target: { value: 'lead-1' } });
  fireEvent.click(screen.getByRole('button', { name: 'Create Deal' }));
  await waitFor(() => expect(mocks.create).toHaveBeenCalledTimes(1));
  expect(screen.getByLabelText('Lead *')).toHaveValue('lead-1');
  fireEvent.click(screen.getByRole('button', { name: 'Create Deal' }));
  await waitFor(() => expect(screen.queryByLabelText('Lead *')).not.toBeInTheDocument());
});

it('shows a query failure with retry instead of an empty pipeline', () => {
  mocks.error = new Error('Offline');
  render(<Pipeline />);
  expect(screen.getByRole('alert')).toHaveTextContent('Unable to load deals: Offline');
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  expect(mocks.refetch).toHaveBeenCalled();
});
