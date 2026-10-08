import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.api }));
import { RetellBatchDialog } from '@/components/leads/RetellBatchDialog';
const ready = { lead_id: 'lead-1', property_address: 'TEST ONLY', phone_number: '+12145559970',
  can_review: false, can_call: true, blockers: [], consent: { accepted: true, disclosure: 'Saved explicit AI permission', submitted_at: '2026-10-07' } };
const batch = { id: 'saved-batch', lead_ids: ['lead-1'], status: 'ready',
  outcomes: [{ lead_id: 'lead-1', request_id: 'saved-reference', phone_number: ready.phone_number, status: 'pending' }] };
const response = (state: unknown) => ({ json: async () => state });
beforeEach(() => mocks.api.mockReset());
afterEach(cleanup);

it('shows actual blockers without creating or dispatching a call batch', async () => {
  mocks.api.mockResolvedValueOnce(response(null)).mockResolvedValueOnce(response({ leads: [{ ...ready, can_call: false, blockers: ['Calling disabled'] }] }));
  render(<RetellBatchDialog leadIds={['lead-1']} onClose={() => {}} />);
  await screen.findByText('Calling disabled');
  expect(screen.getByRole('button', { name: 'Start reviewed batch' })).toBeDisabled();
  expect(mocks.api.mock.calls.map(call => call[0])).toEqual(['/api/calls/retell/batch/recent', '/api/calls/retell/batch/preview']);
});

it('requires acknowledgement and stops after an uncertain dispatch response', async () => {
  mocks.api.mockResolvedValueOnce(response(null)).mockResolvedValueOnce(response({ leads: [ready] }))
    .mockResolvedValueOnce(response(batch)).mockRejectedValueOnce(new Error('Unconfirmed provider outcome'))
    .mockResolvedValueOnce(response({ ...batch, status: 'review', outcomes: [{ ...batch.outcomes[0], status: 'unknown' }] }));
  render(<RetellBatchDialog leadIds={['lead-1']} onClose={() => {}} />);
  await screen.findByText('Saved explicit AI permission');
  const start = screen.getByRole('button', { name: 'Start reviewed batch' });
  expect(start).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(start);
  await screen.findByText('Unconfirmed provider outcome');
  await screen.findByText('Saved batch: review');
  expect(mocks.api.mock.calls.filter(call => call[0].endsWith('/next'))).toHaveLength(1);
  expect(mocks.api.mock.calls.filter(call => call[0] === '/api/calls/retell/batch')).toHaveLength(1);
  expect(screen.queryByRole('button', { name: 'Continue remaining calls' })).not.toBeInTheDocument();
});

it('resumes a durable batch without automatically placing another call', async () => {
  mocks.api.mockResolvedValueOnce(response({ ...batch, status: 'processing' })).mockResolvedValueOnce(response({ leads: [ready] }));
  render(<RetellBatchDialog leadIds={[]} onClose={() => {}} />);
  await screen.findByText('Saved batch: processing');
  await waitFor(() => expect(mocks.api).toHaveBeenCalledTimes(2));
  expect(mocks.api.mock.calls.every(call => !call[0].endsWith('/next'))).toBe(true);
  expect(mocks.api.mock.calls.filter(call => call[0] === '/api/calls/retell/batch')).toHaveLength(0);
});

it('closing after dispatch starts prevents subsequent browser dispatches', async () => {
  let resolveNext!: (value: unknown) => void;
  mocks.api.mockResolvedValueOnce(response(null)).mockResolvedValueOnce(response({ leads: [ready] }))
    .mockResolvedValueOnce(response(batch)).mockImplementationOnce(() => new Promise(resolve => { resolveNext = resolve; }));
  const view = render(<RetellBatchDialog leadIds={['lead-1']} onClose={() => {}} />);
  await screen.findByText('Saved explicit AI permission');
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button', { name: 'Start reviewed batch' }));
  await waitFor(() => expect(mocks.api.mock.calls.filter(call => call[0].endsWith('/next'))).toHaveLength(1));
  view.unmount(); resolveNext(response(batch));
  await Promise.resolve(); await Promise.resolve();
  expect(mocks.api.mock.calls.filter(call => call[0].endsWith('/next'))).toHaveLength(1);
});

it('requires a successful refresh after both dispatch and status reads are uncertain', async () => {
  mocks.api.mockResolvedValueOnce(response(null)).mockResolvedValueOnce(response({ leads: [ready] }))
    .mockResolvedValueOnce(response(batch)).mockRejectedValueOnce(new Error('Unconfirmed provider outcome'))
    .mockRejectedValueOnce(new Error('Database unavailable'));
  render(<RetellBatchDialog leadIds={['lead-1']} onClose={() => {}} />);
  await screen.findByText('Saved explicit AI permission');
  fireEvent.click(screen.getByRole('checkbox')); fireEvent.click(screen.getByRole('button', { name: 'Start reviewed batch' }));
  await screen.findByText('Unconfirmed provider outcome');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Continue remaining calls' })).toBeDisabled());
  expect(mocks.api.mock.calls.filter(call => call[0].endsWith('/next'))).toHaveLength(1);
});

it('recovers initial readiness failure by checking the saved batch before enabling controls', async () => {
  mocks.api.mockRejectedValueOnce(new Error('Initial status unavailable'));
  render(<RetellBatchDialog leadIds={['lead-1']} onClose={() => {}} />);
  await screen.findByText('Initial status unavailable');
  expect(screen.getByRole('button', { name: 'Start reviewed batch' })).toBeDisabled();
  mocks.api.mockResolvedValueOnce(response({ ...batch, status: 'processing' })).mockResolvedValueOnce(response({ leads: [ready] }));
  fireEvent.click(screen.getByRole('button', { name: 'Refresh and reconcile' }));
  await screen.findByText('Saved batch: processing');
  expect(mocks.api.mock.calls.filter(call => call[0].endsWith('/next'))).toHaveLength(0);
  expect(mocks.api.mock.calls.filter(call => call[0] === '/api/calls/retell/batch/recent')).toHaveLength(2);
});
