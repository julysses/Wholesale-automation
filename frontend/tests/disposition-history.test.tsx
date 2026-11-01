import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DispositionReviewHistory } from '../src/components/acquisition/DispositionReviewHistory';
import { parseDispositionHistory, parseDispositionHistoryDetail } from '../src/lib/acquisition/disposition-history';
import { dispositionId as id, dispositionContext as context, dispositionHistorySummary as summary, dispositionHistoryRecord as detail, dispositionHistoryEnvelope as envelope } from './fixtures/disposition-review';
const mock = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch }));
beforeEach(() => {
  mock.fetch.mockReset(); mock.fetch.mockImplementation(async (path: string) => {
    if (path.endsWith('/'+id(102))) return { json: async () => ({ ...envelope, record: detail(2, 'withdrawn') }) };
    if (path.endsWith('/'+id(101))) return { json: async () => ({ ...envelope, record: detail(1, 'requires_resolution') }) };
    return { json: async () => ({ ...envelope, items: [summary(2, 'withdrawn'), summary(1, 'requires_resolution')], next_before: null }) };
  });
});
function open(disabled = false) { return render(<QueryClientProvider client={new QueryClient()}><DispositionReviewHistory context={context} disabled={disabled} /></QueryClientProvider>); }
it('shows recorded hold actions and follows a withdrawal to its original decision without writes', async () => {
  open(); expect(mock.fetch).not.toHaveBeenCalled(); fireEvent.click(screen.getByText('View disposition history'));
  fireEvent.click(await screen.findByText('Read decision 2')); await screen.findByText('Original decision 2 · Decision withdrawn');
  fireEvent.click(screen.getByText('Read the withdrawn original decision')); await screen.findByText('Original decision 1 · Resolution hold recorded');
  expect(screen.getByText(/Obtain counsel review/)).toBeVisible(); expect(screen.getByText(/Recorded approvals are historical/)).toBeVisible();
  expect(mock.fetch.mock.calls.every(call => !call[1]?.method || call[1].method === 'GET')).toBe(true);
  fireEvent.click(screen.getByText('Close disposition history')); expect(screen.queryByText(/Obtain counsel/)).not.toBeInTheDocument();
});
it('renders an expired approval as historical evidence without current authority', async () => {
  mock.fetch.mockImplementation(async (path: string) => ({ json: async () => path.includes('?') ? { ...envelope, items: [summary()], next_before: null } : { ...envelope, record: detail() } }));
  open(); fireEvent.click(screen.getByText('View disposition history')); fireEvent.click(await screen.findByText('Read decision 1'));
  await screen.findByText(/Original approval expiry:/); expect(screen.getByText(/This does not establish current approval/)).toBeVisible();
});
it('removes stale contents on read failure and allows explicit refresh', async () => {
  open(); fireEvent.click(screen.getByText('View disposition history')); await screen.findByText('Read decision 1');
  mock.fetch.mockRejectedValue(new Error('Session revoked')); fireEvent.click(screen.getByText('Refresh disposition history'));
  await screen.findByRole('alert'); expect(screen.queryByText('Read decision 1')).not.toBeInTheDocument();
});
it('does not read while an adjacent contract step is pending', () => { open(true); expect(screen.getByText('View disposition history')).toBeDisabled(); expect(mock.fetch).not.toHaveBeenCalled(); });
it('uses the last recorded sequence for bounded descending pages', async () => {
  mock.fetch.mockImplementation(async (path: string) => ({ json: async () => path.includes('before=2') ? { ...envelope, items: [summary(1)], next_before: null }
    : { ...envelope, items: Array.from({ length: 20 }, (_, i) => summary(21 - i)), next_before: 2 } }));
  open(); fireEvent.click(screen.getByText('View disposition history')); await screen.findByText('Read decision 21'); fireEvent.click(screen.getByText('Older disposition decisions')); await screen.findByText('Read decision 1');
  expect(mock.fetch.mock.calls[1][0]).toContain('limit=20&before=2'); expect(screen.getByText('Older disposition decisions')).toBeDisabled();
  fireEvent.click(screen.getByText('Newer disposition decisions')); await waitFor(() => expect(screen.getByText('Read decision 21')).toBeVisible());
});
it.each(['workspace', 'version', 'order', 'duplicate', 'cursor', 'authority', 'future'])('rejects unsafe history page %s', issue => {
  const value = { ...envelope, items: [summary(3), summary(2)], next_before: null as number | null };
  if (issue === 'workspace') value.items[0].workspace_id = id(88);
  if (issue === 'version') value.contract_version = 1;
  if (issue === 'order') value.items.reverse();
  if (issue === 'duplicate') value.items[1].id = value.items[0].id;
  if (issue === 'cursor') value.next_before = 2;
  if (issue === 'authority') value.approval_current = true;
  if (issue === 'future') value.items[0].created_at = new Date(Date.now() + 60000).toISOString();
  expect(() => parseDispositionHistory(value, context)).toThrow();
});
it.each(['source', 'scan', 'missing', 'future', 'withdrawal', 'authority', 'identity'])('rejects inconsistent recorded detail %s', issue => {
  const value = { ...envelope, record: detail() }, row = value.record;
  if (issue === 'source') row.disposition_sources![0].sha256 = 'b'.repeat(64);
  if (issue === 'scan') row.verification_id = id(88);
  if (issue === 'missing') row.disposition_findings = null;
  if (issue === 'future') row.source_version = 3;
  if (issue === 'withdrawal') row.disposition_original_review_id = id(88);
  if (issue === 'authority') value.execution_authorized = true;
  if (issue === 'identity') row.id = id(88);
  expect(() => parseDispositionHistoryDetail(value, context, id(101))).toThrow();
});

it.each(['exit', 'title', 'expiry', 'contract_citation', 'duplicate_source', 'source_version', 'private_snapshot', 'withdrawal_findings'])('rejects disposition-specific historical mismatch %s', issue => {
  const value = { ...envelope, record: detail(issue === 'withdrawal_findings' ? 2 : 1, issue === 'withdrawal_findings' ? 'withdrawn' : 'approved') }, row = value.record;
  if (issue === 'exit') row.disposition_exit_type = 'principal_acquisition';
  if (issue === 'title') row.disposition_title_status = 'requires_resolution';
  if (issue === 'expiry') row.disposition_sources![0].expires_at = new Date(Date.parse(row.expires_at!) - 1000).toISOString();
  if (issue === 'contract_citation') {
    row.disposition_sources!.push({ ...row.disposition_sources![0], artifact_id: id(99) });
    row.disposition_findings!.contractual_interest.sources[0].artifact_id = id(99);
  }
  if (issue === 'duplicate_source') row.disposition_sources!.push({ ...row.disposition_sources![0] });
  if (issue === 'source_version') row.disposition_findings!.contractual_interest.sources[0].artifact_version = 2;
  if (issue === 'private_snapshot') Object.assign(row, { disposition_policy_snapshot: {} });
  if (issue === 'withdrawal_findings') row.disposition_findings = detail().disposition_findings;
  expect(() => parseDispositionHistoryDetail(value, context, row.id)).toThrow();
});
it('retains principal findings without assignment requirements or current authority', () => {
  const record = detail(1, 'approved', false);
  const parsed = parseDispositionHistoryDetail({ ...envelope, record }, context, record.id);
  expect(parsed.record.disposition_findings?.assignment).toBeNull(); expect(parsed.approval_current).toBe(false);
});
it('rejects invalid observation time even for an empty history page', () => {
  expect(() => parseDispositionHistory({ ...envelope, items: [], next_before: null }, context, null, NaN)).toThrow();
});
