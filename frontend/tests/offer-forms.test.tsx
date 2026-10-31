import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { OfferForms } from '../src/components/acquisition/OfferForms';
import { CampaignDrafts } from '../src/components/acquisition/CampaignDrafts';
import { ApiError } from '@/lib/api';
const mock = vi.hoisted(() => ({ fetch: vi.fn(), post: vi.fn(), role: 'owner', page: {} as unknown }));
vi.mock('@/lib/api', () => ({ apiFetch: mock.fetch, ApiError: class extends Error { status = 403; } }));
const workspace = '11111111-1111-4111-8111-111111111111';
const campaign = '22222222-2222-4222-8222-222222222222';
const key = `acquisition-offer-form-request:v1:user:${workspace}:${campaign}`;
const definition = { form_key: campaign, version: 'v1', privacy_acknowledged: 'Synthetic privacy wording', human_callback_requested: 'Synthetic optional human callback', email_reply_requested: 'Synthetic optional email reply' };
const draft = { id: campaign, expected_revision: 0, definition };
const row = { id: campaign, workspace_id: workspace, campaign_id: campaign, acquisition_form_key: campaign, acquisition_form_revision: 1, acquisition_form_version: 'v1', acquisition_form_definition: definition, acquisition_definition_hash: 'a'.repeat(64), created_at: '2026-10-31T14:00:00Z', active: false, send_confirmation_sms: false, send_confirmation_email: false };
function receipt(d: typeof draft) { return { id: d.id, workspace_id: workspace, campaign_id: campaign, form_key: d.definition.form_key, revision: d.expected_revision + 1, version: d.definition.version, definition_hash: 'a'.repeat(64), status: 'draft', duplicate: false, public_enabled: false, execution_authorized: false }; }
beforeEach(() => {
  sessionStorage.clear(); mock.role = 'owner'; mock.page = { items: [], next_after: null }; mock.fetch.mockReset(); mock.post.mockReset();
  mock.post.mockImplementation(async (init: RequestInit) => receipt(JSON.parse(init.body as string)));
  mock.fetch.mockImplementation(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') return { json: () => mock.post(init) };
    return { json: async () => path.endsWith('/memberships') ? [{ workspace_id: workspace, user_id: 'user', role: mock.role, status: 'active' }] : mock.page };
  });
});
function view(userId = 'user', onPending = vi.fn()) { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><OfferForms userId={userId} workspace={workspace} campaign={campaign} onPending={onPending}/></QueryClientProvider>); }
async function fill() {
  fireEvent.click(screen.getByRole('button', { name: 'Set up request form' }));
  await waitFor(() => expect(screen.getByLabelText('Privacy acknowledgement wording')).toBeEnabled());
  for (const [label, value] of [['Privacy acknowledgement wording', definition.privacy_acknowledged], ['Optional human callback wording', definition.human_callback_requested], ['Optional email reply wording', definition.email_reply_requested]]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
}
it('prepares a form through numbered steps without public or contact authority', async () => {
  view(); await fill(); expect(screen.getByText('1. Explain how the inquiry will be used')).toBeVisible(); expect(screen.getByText('2. Keep reply choices separate')).toBeVisible(); expect(screen.getByText('3. Review this version')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Save form for review' })); await screen.findByText(/Form version 1 saved for review/);
  const sent = JSON.parse(mock.post.mock.calls[0][0].body); expect(Object.keys(sent).sort()).toEqual(['definition', 'expected_revision', 'id']); expect(sent.definition).toMatchObject({ ...definition, form_key: expect.any(String) }); expect(sessionStorage.getItem(key)).toBeNull(); expect(screen.queryByRole('button', { name: /publish/i })).toBeNull();
});
it('retains exact wording through uncertain response, refresh and remount', async () => {
  mock.post.mockRejectedValueOnce(new Error('timeout')); const first = view(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save form for review' })); await screen.findByText(/Save is unconfirmed/);
  const sent = mock.post.mock.calls[0][0].body; expect(sessionStorage.getItem(key)).toBe(sent); fireEvent.click(screen.getByRole('button', { name: 'Refresh form setup' })); expect(screen.getByLabelText('Privacy acknowledgement wording')).toBeDisabled(); first.unmount(); view(); fireEvent.click(screen.getByRole('button', { name: 'Retry exact form save' })); await screen.findByText(/Form version 1 saved/); expect(mock.post.mock.calls[1][0].body).toBe(sent);
});
it('holds an uncertain retry after authority is revoked', async () => {
  sessionStorage.setItem(key, JSON.stringify(draft)); mock.role = 'operator'; mock.post.mockRejectedValue(new ApiError('revoked', 403)); view(); fireEvent.click(screen.getByRole('button', { name: 'Retry exact form save' })); await screen.findByText(/Save is unconfirmed/); expect(sessionStorage.getItem(key)).toBe(JSON.stringify(draft));
});
it('clears only a definitively rejected first attempt', async () => {
  mock.post.mockRejectedValue(new ApiError('revoked', 403)); view(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save form for review' })); await screen.findByText(/Save rejected/); expect(sessionStorage.getItem(key)).toBeNull();
});
it('blocks saves when wording or version is invalid', async () => {
  view(); await fill(); fireEvent.change(screen.getByLabelText('Optional email reply wording'), { target: { value: ' ' } }); expect(screen.getByRole('button', { name: 'Save form for review' })).toBeDisabled(); fireEvent.change(screen.getByLabelText('Optional email reply wording'), { target: { value: definition.email_reply_requested } }); fireEvent.change(screen.getByLabelText('Version label'), { target: { value: 'bad label' } }); expect(screen.getByRole('button', { name: 'Save form for review' })).toBeDisabled();
});
it('does not send if durable browser storage fails', async () => {
  view(); await fill(); const fail = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked'); }); fireEvent.click(screen.getByRole('button', { name: 'Save form for review' })); await screen.findByText(/No save was sent/); expect(mock.post).not.toHaveBeenCalled(); fail.mockRestore();
});
it('preserves pending state if clearing storage fails after a successful response', async () => {
  view(); await fill(); const fail = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => { throw new Error('blocked'); }); fireEvent.click(screen.getByRole('button', { name: 'Save form for review' })); await screen.findByText(/Save is unconfirmed/); expect(sessionStorage.getItem(key)).not.toBeNull(); expect(screen.getByLabelText('Version label')).toBeDisabled(); fail.mockRestore();
});
it('rejects corrupt pending data and isolates another user', () => {
  sessionStorage.setItem(key, '{invalid'); const first = view(); expect(screen.getByRole('alert')).toHaveTextContent('Saved form request cannot be read'); expect(screen.getByRole('button', { name: 'Save form for review' })).toBeDisabled(); first.unmount(); view('other-user'); expect(screen.queryByRole('alert')).toBeNull();
});
it.each(['operator', 'acquisition_caller', 'agency_manager'])('does not permit %s to create a form version', async role => {
  mock.role = role; view(); fireEvent.click(screen.getByRole('button', { name: 'Set up request form' })); await screen.findByText(/Saving form versions requires/); expect(screen.getByLabelText('Privacy acknowledgement wording')).toBeDisabled();
});
it.each([{ workspace_id: 'other' }, { active: true }, { send_confirmation_sms: true }, { acquisition_form_version: 'v2' }, { acquisition_form_revision: true }])('rejects inconsistent history %j', async override => {
  mock.page = { items: [{ ...row, ...override }], next_after: null }; view(); fireEvent.click(screen.getByRole('button', { name: 'Set up request form' })); await screen.findByText('Saved form history could not be verified.'); expect(screen.queryByText('Version 1 · v1')).toBeNull(); expect(screen.getByRole('button', { name: 'Save form for review' })).toBeDisabled();
});
it('renders saved wording as text and creates the next immutable version', async () => {
  mock.page = { items: [{ ...row, acquisition_form_definition: { ...definition, privacy_acknowledged: '<img src=x>' } }], next_after: null }; const rendered = view(); await fill(); fireEvent.click(screen.getByText('View saved wording')); expect(rendered.container.querySelector('img')).toBeNull(); fireEvent.click(screen.getByRole('button', { name: 'Prepare next version from v1' })); expect(screen.getByLabelText('Version label')).toHaveValue('v2'); fireEvent.click(screen.getByRole('button', { name: 'Save form for review' })); await screen.findByText(/Form version 2 saved/); const sent = JSON.parse(mock.post.mock.calls[0][0].body); expect(sent.expected_revision).toBe(1); expect(sent.definition.form_key).toBe(campaign); expect(sent.definition.privacy_acknowledged).toBe('<img src=x>');
});
it.each([{ campaign_id: 'other' }, { public_enabled: true }, { duplicate: 'false' }, { revision: 9 }, { definition_hash: 'invalid' }])('retains a mismatched save receipt %j', async override => {
  mock.post.mockImplementation(async (init: RequestInit) => ({ ...receipt(JSON.parse(init.body as string)), ...override })); view(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Save form for review' })); await screen.findByText(/Save is unconfirmed/); expect(sessionStorage.getItem(key)).not.toBeNull();
});
it('holds campaign navigation and workspace handoff while a form request is unresolved', async () => {
  sessionStorage.setItem(key, JSON.stringify(draft)); const report = vi.fn(); mock.fetch.mockImplementation(async (path: string) => ({ json: async () => path.endsWith('/memberships') ? [{ workspace_id: workspace, user_id: 'user', role: 'owner', status: 'active' }] : path.includes('/offer-forms') ? { items: [], next_after: null } : { items: [{ id: campaign, workspace_id: workspace, name: 'Seller inquiries', status: 'draft', acquisition_channel: 'online_offer', acquisition_budget_cents: 0, acquisition_currency: 'USD' }], next_after: null } }));
  render(<QueryClientProvider client={new QueryClient()}><CampaignDrafts userId="user" workspace={workspace} onPending={report}/></QueryClientProvider>); await screen.findByText(/Finish reconciling the saved preparation request/); expect(report).toHaveBeenLastCalledWith(true); expect(screen.getByRole('button', { name: 'Refresh campaigns' })).toBeDisabled(); expect(screen.getByRole('button', { name: 'Next campaigns' })).toBeDisabled(); expect(screen.getByLabelText('Campaign name')).toBeDisabled();
});
