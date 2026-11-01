import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TitleReviewHistory } from '../src/components/acquisition/TitleReviewHistory';
import { parseTitleHistory, parseTitleHistoryDetail } from '../src/lib/acquisition/title-history';
import { titleId as id, titleContext as context, titleHistorySummary as summary, titleHistoryRecord as detail, titleHistoryEnvelope as envelope } from './fixtures/title-review';
const mock = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch }));
beforeEach(() => {
  mock.fetch.mockReset(); mock.fetch.mockImplementation(async (path: string) => {
    if (path.endsWith('/'+id(102))) return { json: async () => ({ ...envelope, record: detail(2, 'withdrawn') }) };
    if (path.endsWith('/'+id(101))) return { json: async () => ({ ...envelope, record: detail(1, 'requires_resolution') }) };
    return { json: async () => ({ ...envelope, items: [summary(2, 'withdrawn'), summary(1, 'requires_resolution')], next_before: null }) };
  });
});
function open(disabled = false) { return render(<QueryClientProvider client={new QueryClient()}><TitleReviewHistory context={context} disabled={disabled} /></QueryClientProvider>); }
it('shows recorded hold actions and follows a withdrawal to its original decision without writes', async () => {
  open(); expect(mock.fetch).not.toHaveBeenCalled(); fireEvent.click(screen.getByText('View title history'));
  fireEvent.click(await screen.findByText('Read decision 2')); await screen.findByText('Original decision 2 · Decision withdrawn');
  fireEvent.click(screen.getByText('Read the withdrawn original decision')); await screen.findByText('Original decision 1 · Resolution hold recorded');
  expect(screen.getByText(/Obtain the missing original deed/)).toBeVisible(); expect(screen.getByText(/Recorded approvals are historical/)).toBeVisible();
  expect(mock.fetch.mock.calls.every(call => !call[1]?.method || call[1].method === 'GET')).toBe(true);
  fireEvent.click(screen.getByText('Close title history')); expect(screen.queryByText(/Obtain the missing/)).not.toBeInTheDocument();
});
it('renders an expired approval as historical evidence without current authority', async () => {
  mock.fetch.mockImplementation(async (path: string) => ({ json: async () => path.includes('?') ? { ...envelope, items: [summary()], next_before: null } : { ...envelope, record: detail() } }));
  open(); fireEvent.click(screen.getByText('View title history')); fireEvent.click(await screen.findByText('Read decision 1'));
  await screen.findByText(/Original approval expiry:/); expect(screen.getByText(/This does not establish current approval/)).toBeVisible();
});
it('removes stale contents on read failure and allows explicit refresh', async () => {
  open(); fireEvent.click(screen.getByText('View title history')); await screen.findByText('Read decision 1');
  mock.fetch.mockRejectedValue(new Error('Session revoked')); fireEvent.click(screen.getByText('Refresh title history'));
  await screen.findByRole('alert'); expect(screen.queryByText('Read decision 1')).not.toBeInTheDocument();
});
it('does not read while an adjacent contract step is pending', () => { open(true); expect(screen.getByText('View title history')).toBeDisabled(); expect(mock.fetch).not.toHaveBeenCalled(); });
it('uses the last recorded sequence for bounded descending pages', async () => {
  mock.fetch.mockImplementation(async (path: string) => ({ json: async () => path.includes('before=2') ? { ...envelope, items: [summary(1)], next_before: null }
    : { ...envelope, items: Array.from({ length: 20 }, (_, i) => summary(21 - i)), next_before: 2 } }));
  open(); fireEvent.click(screen.getByText('View title history')); await screen.findByText('Read decision 21'); fireEvent.click(screen.getByText('Older title decisions')); await screen.findByText('Read decision 1');
  expect(mock.fetch.mock.calls[1][0]).toContain('limit=20&before=2'); expect(screen.getByText('Older title decisions')).toBeDisabled();
  fireEvent.click(screen.getByText('Newer title decisions')); await waitFor(() => expect(screen.getByText('Read decision 21')).toBeVisible());
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
  expect(() => parseTitleHistory(value, context)).toThrow();
});
it.each(['source', 'scan', 'missing', 'future', 'withdrawal', 'authority', 'identity'])('rejects inconsistent recorded detail %s', issue => {
  const value = { ...envelope, record: detail() }, row = value.record;
  if (issue === 'source') row.title_sources![0].sha256 = 'b'.repeat(64);
  if (issue === 'scan') row.verification_id = id(88);
  if (issue === 'missing') row.title_findings = null;
  if (issue === 'future') row.source_version = 3;
  if (issue === 'withdrawal') row.title_original_review_id = id(88);
  if (issue === 'authority') value.execution_authorized = true;
  if (issue === 'identity') row.id = id(88);
  expect(() => parseTitleHistoryDetail(value, context, id(101))).toThrow();
});
