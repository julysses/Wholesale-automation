import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { sendOutreachBatches, outreachResultText } from '@/lib/outreachBatches';

const mocks = vi.hoisted(() => ({ api: vi.fn(), success: vi.fn(), warning: vi.fn(), error: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.api }));
vi.mock('sonner', () => ({ toast: mocks }));
import { OutreachLauncher } from '@/components/buyers/OutreachLauncher';

const reply = (sent: number, extra: Record<string, number> = {}) => ({
  json: async () => ({ sent_count: sent, failed_count: 0, skipped_count: 0, dry_run_count: 0, log_failed_count: 0, ...extra }),
});

beforeEach(() => { vi.clearAllMocks(); mocks.api.mockReset(); });

it('preserves confirmed counts when apiFetch throws on a later batch and stops additional sends', async () => {
  mocks.api.mockResolvedValueOnce(reply(5)).mockRejectedValueOnce(new Error('Request failed (503)'));
  const result = await sendOutreachBatches('/api/buyers/outreach/sms', 'buyer_ids', Array.from({ length: 12 }, (_, i) => `buyer-${i}`));
  expect(result).toMatchObject({ sent: 5, unresolved: 5, unattempted: 2, interrupted: true, error: 'Request failed (503)' });
  expect(mocks.api).toHaveBeenCalledTimes(2);
  expect(outreachResultText(result)).toContain('unknown recipients may already have received it');
});

it('uses selected lead IDs, deduplicates recipients, and reports dry-run and logging failures', async () => {
  mocks.api.mockResolvedValueOnce(reply(1, { dry_run_count: 1, log_failed_count: 1 }));
  const result = await sendOutreachBatches('/api/marketing/bulk-sms-warm', 'lead_ids', ['lead-a', 'lead-b', 'lead-a']);
  expect(JSON.parse(mocks.api.mock.calls[0][1].body)).toEqual({ lead_ids: ['lead-a', 'lead-b'] });
  expect(result).toMatchObject({ sent: 1, dryRun: 1, logFailed: 1, interrupted: false });
  expect(outreachResultText(result)).toContain('1 activity-log updates failed');
});

it('stops on legacy queued responses or malformed partial counts instead of claiming success', async () => {
  mocks.api.mockResolvedValueOnce({ json: async () => ({ status: 'queued', recipient_count: 6 }) });
  const result = await sendOutreachBatches('/api/buyers/outreach/email', 'buyer_ids', ['a', 'b', 'c', 'd', 'e', 'f']);
  expect(result).toMatchObject({ sent: 0, interrupted: true, unresolved: 5, unattempted: 1 });
  expect(mocks.api).toHaveBeenCalledTimes(1);
});

it('shows interrupted buyer sends without a resend button or automatic navigation', async () => {
  mocks.api.mockResolvedValueOnce(reply(5)).mockRejectedValueOnce(new Error('Network interrupted'));
  const onSent = vi.fn();
  render(<OutreachLauncher buyerIds={['a', 'b', 'c', 'd', 'e', 'f']} onSent={onSent} />);
  fireEvent.click(screen.getByRole('button', { name: 'Send SMS to 6 Buyers' }));
  await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('5 accepted by provider'));
  expect(screen.getByRole('alert')).toHaveTextContent('1 recipients have unknown results');
  expect(screen.queryByRole('button', { name: /Send Another|Send SMS to/ })).not.toBeInTheDocument();
  expect(onSent).not.toHaveBeenCalled();
  expect(mocks.success).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Review outreach activity' }));
  expect(onSent).toHaveBeenCalledOnce();
});

it('sends the edited email and exposes logging failures as warnings', async () => {
  mocks.api.mockResolvedValueOnce(reply(1, { log_failed_count: 1 }));
  render(<OutreachLauncher buyerIds={['a']} />);
  fireEvent.click(screen.getByRole('button', { name: 'EMAIL', exact: true }));
  fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'Operator subject' } });
  fireEvent.change(screen.getByLabelText('Email Body'), { target: { value: 'Operator body' } });
  fireEvent.click(screen.getByRole('button', { name: 'Send EMAIL to 1 Buyers' }));
  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('1 activity-log updates failed'));
  expect(JSON.parse(mocks.api.mock.calls[0][1].body)).toMatchObject({ custom_subject: 'Operator subject', custom_message: 'Operator body' });
  expect(mocks.warning).toHaveBeenCalled();
  expect(mocks.success).not.toHaveBeenCalled();
});
