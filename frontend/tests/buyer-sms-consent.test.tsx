import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.api }));
import { BuyerSmsConsent } from '@/components/buyers/BuyerSmsConsent';
const status = (extra = {}) => ({ buyer_id: 'A', phone: '+12145550731', can_review: true, consent_ready: false,
  suppressed: false, receipt_id: null, accepted: null, recorded_at: null, sending_available: false, evidence: null, ...extra });
const response = (data: unknown) => ({ ok: true, json: async () => data });
const mount = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}><BuyerSmsConsent buyerId="A" /></QueryClientProvider>);
beforeEach(() => { mocks.api.mockReset(); });
it('separates missing consent from sending approval and offers administrator review', async () => {
  mocks.api.mockResolvedValue(response(status())); mount();
  expect(await screen.findByText('Current number has no accepted written consent review.')).toBeInTheDocument();
  expect(screen.getByText(/SMS sending remains unavailable/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Review written buyer consent' }));
  expect(screen.getByRole('button', { name: 'Save written consent review' })).toBeDisabled();
  expect(mocks.api).toHaveBeenCalledTimes(1);
});
it('does not expose consent approval to a nonadministrator', async () => {
  mocks.api.mockResolvedValue(response(status({ can_review: false }))); mount();
  expect(await screen.findByText('An approved administrator must review written evidence.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Review written buyer consent' })).not.toBeInTheDocument();
});
it.each(['foreign', 'failed'])('does not convert %s reads to no-consent proof', async kind => {
  if (kind === 'foreign') mocks.api.mockResolvedValue(response(status({ buyer_id: 'B' })));
  else mocks.api.mockRejectedValue(new Error('Offline'));
  mount(); await screen.findByRole('alert');
  expect(screen.queryByText('Current number has no accepted written consent review.')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Review written buyer consent' })).not.toBeInTheDocument();
});
it('retains the exact review reference and payload after a lost acknowledgement', async () => {
  mocks.api.mockResolvedValueOnce(response(status())).mockRejectedValueOnce(new Error('Lost response'));
  mount(); fireEvent.click(await screen.findByRole('button', { name: 'Review written buyer consent' }));
  const fill = (name: string, value: string) => fireEvent.change(screen.getByLabelText(name), { target: { value } });
  fill('Retained evidence URL', 'https://evidence.example.test/retained'); fill('Evidence SHA-256', 'a'.repeat(64));
  fill('Consent date and time with time zone', '2026-10-22T10:00:00-05:00');
  fill('Exact written disclosure', 'Written buyer deal alerts disclosure, frequency varies. Reply STOP to opt out.');
  fill('Recorded affirmative buyer action', 'Buyer checked the deal-alert SMS consent box.');
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button', { name: 'Save written consent review' }));
  await screen.findByRole('alert');
  const first = mocks.api.mock.calls[1][1].body;
  const payload = JSON.parse(first);
  mocks.api.mockResolvedValueOnce(response({ id: payload.request_id, buyer_id: 'A', saved: true, accepted: true }))
    .mockResolvedValueOnce(response(status({ consent_ready: true, receipt_id: payload.request_id })));
  fireEvent.click(screen.getByRole('button', { name: 'Save written consent review' }));
  await screen.findByRole('status');
  expect(mocks.api.mock.calls[2][1].body).toBe(first);
  await waitFor(() => expect(screen.getByText(/Written consent review is saved for the current number/)).toBeInTheDocument());
  expect(screen.getByText(/SMS sending remains unavailable/)).toBeInTheDocument();
  expect(mocks.api.mock.calls.every(([url]) => !url.includes('/outreach/'))).toBe(true);
});
it('shows retained evidence as inert text and cannot clear suppression', async () => {
  mocks.api.mockResolvedValue(response(status({ suppressed: true, receipt_id: 'receipt-A', evidence: { disclosure: '<script>alert(1)</script>' } }))); mount();
  expect(await screen.findByText('Phone is suppressed. This screen cannot clear it.')).toBeInTheDocument();
  fireEvent.click(screen.getByText('Saved consent review'));
  expect(screen.getByText('Disclosure: <script>alert(1)</script>')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Review written buyer consent' }));
  fireEvent.click(screen.getByRole('checkbox'));
  expect(screen.getByRole('button', { name: 'Save written consent review' })).toBeDisabled();
});

it('fingerprints an evidence copy locally without uploading or sending it', async () => {
  mocks.api.mockResolvedValue(response(status()));
  const digest = vi.fn().mockResolvedValue(new Uint8Array(32).fill(10).buffer);
  const randomUUID = crypto.randomUUID.bind(crypto);
  vi.stubGlobal('crypto', { randomUUID, subtle: { digest } });
  mount(); fireEvent.click(await screen.findByRole('button', { name: 'Review written buyer consent' }));
  const file = new File(['synthetic written evidence'], 'consent.txt', { type: 'text/plain' });
  Object.defineProperty(file, 'arrayBuffer', { value: async () => new TextEncoder().encode('synthetic written evidence').buffer });
  fireEvent.change(screen.getByLabelText('Select the retained evidence file'), { target: { files: [file] } });
  await waitFor(() => expect(screen.getByLabelText('Evidence SHA-256')).toHaveValue('0a'.repeat(32)));
  expect(digest).toHaveBeenCalledTimes(1);
  expect(mocks.api).toHaveBeenCalledTimes(1);
});

it('shows current consent and sender readiness without sending a message', async () => {
  mocks.api.mockResolvedValue(response(status({ consent_ready: true, sending_available: true }))); mount();
  expect(await screen.findByText('Consent and sender checks are ready. Sending hours and daily limits still apply.')).toBeInTheDocument();
  expect(screen.queryByText(/SMS sending remains unavailable/)).not.toBeInTheDocument();
  expect(mocks.api).toHaveBeenCalledTimes(1);
});
