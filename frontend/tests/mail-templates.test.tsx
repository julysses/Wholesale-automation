import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MailTemplates } from '../src/components/acquisition/MailTemplates';
import { ApiError } from '@/lib/api';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), post: vi.fn(), role: 'operator', page: {} as unknown }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { status = 403; } }));
const workspace = '11111111-1111-4111-8111-111111111111';
const campaign = '22222222-2222-4222-8222-222222222222';
const key = `acquisition-mail-request:v1:user:${workspace}:${campaign}`;
const draft = { id: campaign, template_id: campaign, expected_version: 0, name: 'Letter', format: 'letter', tracking_mode: 'phone', body: 'Call {{tracking_phone}}' };
beforeEach(() => {
  sessionStorage.clear(); mock.role = 'operator'; mock.page = { items: [], next_after: null }; mock.fetch.mockReset(); mock.post.mockReset();
  mock.post.mockImplementation(async (init: RequestInit) => { const d = JSON.parse(init.body as string); return { id: d.id, template_id: d.template_id, version: d.expected_version + 1, workspace_id: workspace, status: 'draft', execution_authorized: false, duplicate: false }; });
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') return { json: () => mock.post(init) };
    return { json: async () => path.endsWith('/memberships') ? [{ workspace_id: workspace, user_id: 'user', role: mock.role, status: 'active' }] : mock.page };
  });
});
function view(userId = 'user') { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MailTemplates userId={userId} workspace={workspace} campaign={campaign}/></QueryClientProvider>); }
async function fill(body = draft.body) {
  fireEvent.click(screen.getByRole('button', { name: 'Edit mail drafts' }));
  await waitFor(() => expect(screen.getByLabelText('Template name')).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Template name'), { target: { value: draft.name } });
  fireEvent.change(screen.getByLabelText('Draft content'), { target: { value: body } });
}
it('lets an operator save a new draft without any approval fields', async () => {
  view(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save mail draft' }));
  await screen.findByText(/Draft version 1 saved/);
  const sent = JSON.parse(mock.post.mock.calls[0][0].body);
  expect(sent.expected_version).toBe(0); expect(sent.body).toBe(draft.body); expect(sent.approved_by).toBeUndefined(); expect(sent.workspace_id).toBeUndefined(); expect(sessionStorage.getItem(key)).toBeNull();
});
it('retains an uncertain request through refresh and remount', async () => {
  mock.post.mockRejectedValueOnce(new Error('timeout')); const first = view(); await fill();
  fireEvent.click(screen.getByRole('button', { name: 'Save mail draft' })); await screen.findByText(/Save is unconfirmed/);
  const sent = mock.post.mock.calls[0][0].body; expect(sessionStorage.getItem(key)).toBe(sent);
  fireEvent.click(screen.getByRole('button', { name: 'Refresh mail drafts' })); expect(screen.getByLabelText('Draft content')).toBeDisabled(); first.unmount();
  view(); fireEvent.click(screen.getByRole('button', { name: 'Retry exact mail save' })); await screen.findByText(/Draft version 1 saved/);
  expect(mock.post.mock.calls[1][0].body).toBe(sent);
});
it('retains a pending request after revoked retry authority', async () => {
  sessionStorage.setItem(key, JSON.stringify(draft)); mock.post.mockRejectedValue(new ApiError('revoked', 403)); view();
  fireEvent.click(screen.getByRole('button', { name: 'Retry exact mail save' })); await screen.findByText(/Save is unconfirmed/);
  expect(sessionStorage.getItem(key)).toBe(JSON.stringify(draft));
});
it('clears a definitively rejected new save', async () => {
  mock.post.mockRejectedValue(new ApiError('revoked', 403)); view(); await fill();
  fireEvent.click(screen.getByRole('button', { name: 'Save mail draft' })); await screen.findByText(/Save rejected/); expect(sessionStorage.getItem(key)).toBeNull();
});
it.each(['No tracking', '{{private_owner}} {{tracking_phone}}', '{{tracking_phone}'])('rejects unsupported template %s', async body => {
  view(); await fill(body); expect(screen.getByRole('button', { name: 'Save mail draft' })).toBeDisabled(); expect(mock.post).not.toHaveBeenCalled();
});
it('fails closed on corrupt saved data and isolates other users', async () => {
  sessionStorage.setItem(key, '{broken'); const first = view(); expect(screen.getByRole('alert')).toHaveTextContent('Saved request cannot be read'); expect(screen.getByRole('button', { name: 'Save mail draft' })).toBeDisabled(); first.unmount();
  view('other-user'); expect(screen.getByRole('button', { name: 'Edit mail drafts' })).toBeEnabled(); expect(screen.queryByRole('alert')).toBeNull();
});
it('does not send when storage cannot persist the request', async () => {
  view(); await fill(); const fail = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); });
  fireEvent.click(screen.getByRole('button', { name: 'Save mail draft' })); await screen.findByText(/No save was sent/); expect(mock.post).not.toHaveBeenCalled(); fail.mockRestore();
});
it('renders history as text and seeds an explicit next version', async () => {
  mock.page = { items: [{ id: campaign, workspace_id: workspace, campaign_id: campaign, acquisition_template_id: campaign, acquisition_template_version: 3, name: 'History', primary_text: '<img src=x> {{tracking_phone}}', acquisition_mail_format: 'postcard', acquisition_tracking_mode: 'phone', status: 'draft' }], next_after: null };
  const result = view(); await fill(); await screen.findByText('History · Version 3'); expect(result.container.querySelector('img')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Edit from version 3' })); fireEvent.click(screen.getByRole('button', { name: 'Save mail draft' })); await screen.findByText(/Draft version 4 saved/);
  expect(JSON.parse(mock.post.mock.calls[0][0].body).expected_version).toBe(3);
});
it('does not expose cross-workspace history or allow callers to edit', async () => {
  mock.role = 'acquisition_caller'; mock.page = { items: [{ workspace_id: 'other', name: 'Private draft' }], next_after: null }; view(); fireEvent.click(screen.getByRole('button', { name: 'Edit mail drafts' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Mail history could not be verified'); expect(screen.queryByText('Private draft')).toBeNull(); expect(screen.getByLabelText('Draft content')).toBeDisabled();
});
it.each([{ workspace_id: 'other' }, { execution_authorized: true }, { version: 9 }, { duplicate: 'false' }])('holds an inconsistent receipt %j', async override => {
  mock.post.mockImplementation(async (init: RequestInit) => { const d = JSON.parse(init.body as string); return { id: d.id, template_id: d.template_id, version: 1, workspace_id: workspace, status: 'draft', execution_authorized: false, duplicate: false, ...override }; });
  view(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save mail draft' })); await screen.findByText(/Save is unconfirmed/);
  expect(sessionStorage.getItem(key)).not.toBeNull(); expect(screen.getByLabelText('Draft content')).toBeDisabled();
});
it('requires the selected landing-page placeholder and preserves postcard format', async () => {
  view(); await fill(); fireEvent.change(screen.getByLabelText('Tracked response'), { target: { value: 'landing_page' } });
  expect(screen.getByRole('button', { name: 'Save mail draft' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Draft content'), { target: { value: 'Visit {{tracking_url}}' } });
  fireEvent.change(screen.getByLabelText('Mail format'), { target: { value: 'postcard' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save mail draft' })); await screen.findByText(/Draft version 1 saved/);
  const sent = JSON.parse(mock.post.mock.calls[0][0].body); expect(sent.format).toBe('postcard'); expect(sent.tracking_mode).toBe('landing_page');
});
