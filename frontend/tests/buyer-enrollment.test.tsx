import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { BuyerEnrollment } from '@/pages/BuyerEnrollment';
import { BuyerEnrollmentAdmin } from '@/components/buyers/BuyerEnrollmentAdmin';
const mocks = vi.hoisted(() => ({ api: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.api }));
const id = '01a16149-82e7-4702-93d5-b5d7708812aa';
const cap = { request_id: id, token: 'a'.repeat(43) };
const program = { brand: 'Synthetic Buyer Program', support: 'support@example.test', origin: 'https://example.test',
  version: 'b'.repeat(64), disclosure: 'Optional written consent for recurring automated buyer deal-alert texts. Reply STOP. Consent is not required to purchase.',
  terms: 'Synthetic program terms. STOP for opt-out; HELP for help.', privacy: 'Synthetic privacy statement. Consent is not shared for other marketing.' };
const reply = (value: unknown) => ({ ok: true, json: async () => value });
function mount(path = '/buyer-sms') { return render(<MemoryRouter initialEntries={[path]}><BuyerEnrollment /></MemoryRouter>); }
beforeEach(() => { mocks.api.mockReset(); window.history.replaceState(null, '', '/buyer-sms#reference=' + id + '&token=' + cap.token); });
function publicApi(saved = false) {
  const fetcher = vi.fn().mockImplementation(async (url: string) => reply(url.endsWith('/config') ? { available: true, program } : { id, saved, accepted: true }));
  vi.stubGlobal('fetch', fetcher); return fetcher;
}
it('shows an unchecked optional choice and exact policies without any operator session', async () => {
  const fetcher = publicApi(); mount();
  await screen.findByText(program.disclosure);
  await waitFor(() => expect(screen.getByLabelText('Your mobile number')).toBeEnabled());
  expect(screen.getByRole('checkbox')).not.toBeChecked();
  expect(screen.getByRole('button', { name: 'Keep buyer SMS off' })).toBeEnabled();
  expect(screen.getByRole('link', { name: 'Privacy Statement' })).toHaveAttribute('href', '/buyer-sms/privacy');
  expect(fetcher.mock.calls.every(([, options]) => !options?.headers?.Authorization)).toBe(true);
});
it('recovers a saved receipt after reload without replaying submission', async () => {
  const fetcher = publicApi(true); mount(); await screen.findByText('Your choice is saved');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(fetcher.mock.calls.some(([url]) => url.endsWith('/submit'))).toBe(false);
});
it('retains the same consumer payload and freezes changes after a lost response', async () => {
  const fetcher = publicApi(); mount();
  await waitFor(() => expect(screen.getByLabelText('Your mobile number')).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Your mobile number'), { target: { value: '(214) 555-0991' } });
  fireEvent.click(screen.getByRole('checkbox'));
  fetcher.mockImplementationOnce(async () => { throw new Error('Lost response'); });
  fireEvent.click(screen.getByRole('button', { name: 'Save my SMS request' }));
  await screen.findByRole('alert');
  expect(screen.getByLabelText('Your mobile number')).toBeDisabled(); expect(screen.getByRole('checkbox')).toBeDisabled();
  const original = fetcher.mock.calls.find(([url]) => url.endsWith('/submit'))![1].body;
  fetcher.mockResolvedValueOnce(reply({ id, saved: true, accepted: true }));
  fireEvent.click(screen.getByRole('button', { name: 'Retry saving the same choice' }));
  await screen.findByText('Your choice is saved');
  expect(fetcher.mock.calls.filter(([url]) => url.endsWith('/submit')).map(([, options]) => options.body)).toEqual([original, original]);
  expect(JSON.parse(original)).toMatchObject({ ...cap, accepted: true, program_version: program.version });
});
it('keeps enrollment unavailable when the approved program cannot be confirmed', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply({ available: false, program: null }))); window.history.replaceState(null, '', '/buyer-sms'); mount();
  await screen.findByText('Enrollment is currently unavailable. Please contact the program operator.');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
});
it('makes policy pages public without displaying a buyer form or record', async () => {
  publicApi(); window.history.replaceState(null, '', '/buyer-sms/privacy'); mount('/buyer-sms/privacy');
  await screen.findByText(program.privacy); expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
});
it('requires a confirmed invitation before revealing its private link and never sends it', async () => {
  mocks.api.mockImplementation(async (url: string, options?: RequestInit) => reply(url.endsWith('enrollment-program') ? { available: true, program } : url.includes('enrollment-submissions') ?
    { buyer_id: 'A', total: 0, offset: 0, submissions: [] } : { id: JSON.parse(options?.body as string).request_id, buyer_id: 'A', saved: true }));
  render(<BuyerEnrollmentAdmin buyerId="A" onReviewed={() => {}} />);
  expect(mocks.api).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole('button', { name: 'Prepare buyer enrollment' }));
  await screen.findByRole('button', { name: 'Create private enrollment link' });
  fireEvent.click(screen.getByRole('button', { name: 'Create private enrollment link' }));
  const link = await screen.findByLabelText('Private buyer enrollment link');
  expect((link as HTMLInputElement).value).toMatch(/^https:\/\/example.test\/buyer-sms#reference=.*&token=[A-Za-z0-9_-]{43}$/);
  expect(screen.getByText(/No invitation was sent/)).toBeInTheDocument();
  expect(mocks.api.mock.calls.every(([url]) => !url.includes('/outreach/'))).toBe(true);
});

it('allows number correction only after a rejected choice and a confirmed empty receipt', async () => {
  const fetcher = publicApi(); mount();
  await waitFor(() => expect(screen.getByLabelText('Your mobile number')).toBeEnabled());
  fireEvent.change(screen.getByLabelText('Your mobile number'), { target: { value: '+12145550992' } });
  fetcher.mockResolvedValueOnce({ ok: false, status: 409, json: async () => ({ detail: 'Link unavailable' }) });
  fireEvent.click(screen.getByRole('button', { name: 'Keep buyer SMS off' }));
  await screen.findByText('Your choice was not saved. Check your number or request a new enrollment link.');
  expect(screen.getByLabelText('Your mobile number')).toBeEnabled();
  expect(screen.getByRole('checkbox')).not.toBeChecked();
});
