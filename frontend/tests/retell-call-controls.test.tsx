import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import type { Lead } from '@/types';
const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.api }));
import { RetellCallDialog } from '@/components/leads/RetellCallDialog';
const lead = { id: 'test-lead', property_address: 'TEST ONLY' } as Lead;
const ready = { phone_number: '+12147010100', ai_calling_paused: false, can_review: false,
  can_call: true, blockers: [], attempt: null, consent: { accepted: true, disclosure: 'Saved explicit AI permission', submitted_at: '2026-10-07' } };
const response = (state: unknown) => ({ json: async () => state });
beforeEach(() => mocks.api.mockReset());
afterEach(cleanup);

it('shows launch blockers without sending a call request', async () => {
  mocks.api.mockResolvedValue(response({ ...ready, can_call: false, blockers: ['Calling disabled'] }));
  render(<RetellCallDialog lead={lead} onClose={() => {}} />);
  await screen.findByText('Calling disabled');
  expect(screen.getByRole('button', { name: 'Start AI call' })).toBeDisabled();
  expect(mocks.api.mock.calls.every(call => !call[1]?.method)).toBe(true);
});

it('requires acknowledgement and separates review from calling', async () => {
  mocks.api.mockResolvedValueOnce(response({ ...ready, ai_calling_paused: true, can_review: true, can_call: false }))
    .mockResolvedValueOnce(response(ready)).mockResolvedValueOnce(response(ready));
  render(<RetellCallDialog lead={lead} onClose={() => {}} />);
  const approve = await screen.findByRole('button', { name: 'Approve lead for AI call' });
  expect(approve).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(approve);
  await screen.findByText(/Starting a call requires a separate action/);
  await waitFor(() => expect(mocks.api).toHaveBeenCalledTimes(3));
  expect(mocks.api.mock.calls.filter(call => call[1]?.method === 'POST').map(call => call[0]))
    .toEqual(['/api/calls/retell/lead/test-lead/review']);
});

it('blocks replacement requests when creation has an unresolved outcome', async () => {
  mocks.api.mockResolvedValueOnce(response(ready)).mockRejectedValueOnce(new Error('Unconfirmed provider outcome'))
    .mockResolvedValueOnce(response({ ...ready, can_call: false, blockers: ['Earlier call unresolved'],
      attempt: { request_id: 'existing-reference', call_id: null, status: 'unknown' } }));
  render(<RetellCallDialog lead={lead} onClose={() => {}} />);
  await screen.findByText('Saved explicit AI permission');
  fireEvent.click(screen.getByRole('button', { name: 'Start AI call' }));
  await screen.findByText('Earlier call unresolved');
  expect(screen.getByRole('button', { name: 'Start AI call' })).toBeDisabled();
  const creations = mocks.api.mock.calls.filter(call => call[0] === '/api/calls/retell');
  expect(creations).toHaveLength(1);
  expect(JSON.parse(creations[0][1].body).request_id).toMatch(/^[0-9a-f-]{36}$/);
});
