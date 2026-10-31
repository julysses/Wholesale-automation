import '@testing-library/jest-dom/vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SellerOfferForm } from './SellerOffer';
import { preserveSellerInquiry, type PendingSellerInquiry } from '@/lib/sellerOfferRequest';

vi.mock('@/components/seller/SellerChallenge', () => ({ SellerChallenge: ({ onToken }: { onToken: (token: string) => void }) =>
  <button type="button" onClick={() => onToken('synthetic-widget-token')}>Verify request</button> }));
const definition = { form_key: 'synthetic', version: 'v1', privacy_acknowledged: 'I acknowledge the reviewed privacy wording.', human_callback_requested: 'Please request a human callback.', email_reply_requested: 'Please request an email reply.' };
const pending: PendingSellerInquiry = { version: 1, formKey: 'synthetic', savedAt: '2026-10-31T21:00:00Z', definition,
  inquiry: { submission_id: 'fd000000-0000-4000-8000-000000000001', form_version: 'v1',
    seller: { name: 'Synthetic Seller', email: 'seller@example.test' }, property: { address: '123 Synthetic St', city: 'Dallas', state: 'TX', postal_code: '75201', authority: 'owner', condition: 'unsure', occupancy: 'vacant', timeline: 'flexible', motivation: 'Synthetic review', asking_price: null }, selections: { privacy_acknowledged: true, human_callback_requested: false, email_reply_requested: false } } };
const fetcher = vi.fn();
const response = (value: unknown, status = 200) => ({ ok: status === 200, status, json: async () => value, headers: new Headers() });
beforeEach(() => { sessionStorage.clear(); fetcher.mockReset(); vi.stubGlobal('fetch', fetcher); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function fill(label: string, value: string) { fireEvent.change(screen.getByLabelText(label), { target: { value } }); }
async function walkToReview() {
  await screen.findByRole('heading', { name: 'Step 1 of 4 · Property' });
  fill('Street address, including unit if applicable', '123 Synthetic St'); fill('City', 'Dallas'); fill('ZIP code', '75201');
  fill('Your relationship to the property', 'owner'); fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
  fill('Current condition', 'unsure'); fill('Who is living there?', 'vacant'); fill('When would you like to sell?', 'flexible');
  fill('What would you like us to know?', 'Synthetic review'); fireEvent.click(screen.getByRole('button', { name: 'Continue' }));
  fill('Your name', 'Synthetic Seller'); fill('Email address (optional)', 'seller@example.test');
  fireEvent.click(screen.getByLabelText(definition.privacy_acknowledged)); fireEvent.click(screen.getByRole('button', { name: 'Review request' }));
  await screen.findByRole('heading', { name: 'Step 4 of 4 · Review' });
}

describe('guided seller offer request', () => {
  it('walks four steps, waits for verification and confirms only its own received receipt', async () => {
    fetcher.mockImplementation(async (_url, options) => options?.method === 'POST'
      ? response({ submission_id: JSON.parse(options.body).inquiry.submission_id, status: 'received', duplicate: false })
      : response({ definition, bot_site_key: 'public-key' }));
    render(<SellerOfferForm formKey="synthetic" />); await walkToReview();
    expect(screen.getByText('Asking price: Not provided')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Request an offer' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Verify request' }));
    fireEvent.click(screen.getByRole('button', { name: 'Request an offer' }));
    await screen.findByRole('heading', { name: 'Your request is received' });
    const body = JSON.parse(fetcher.mock.calls.find(([, options]) => options?.method === 'POST')![1].body);
    expect(body.inquiry.property.asking_price).toBeNull(); expect(body.inquiry.selections.human_callback_requested).toBe(false);
    expect(Object.keys(body)).toEqual(['inquiry', 'bot_token']); expect(sessionStorage.length).toBe(0);
    expect(screen.getByText(/not a purchase offer/)).toBeInTheDocument();
  });
  it('preserves original request through a lost reply, reload, and duplicate confirmation', async () => {
    const sent: unknown[] = [];
    fetcher.mockImplementation(async (_url, options) => {
      if (options?.method !== 'POST') return response({ definition, bot_site_key: 'public-key' });
      const body = JSON.parse(options.body); sent.push(body.inquiry);
      if (sent.length === 1) throw new TypeError('Synthetic response loss');
      return response({ submission_id: body.inquiry.submission_id, status: 'received', duplicate: true });
    });
    const first = render(<SellerOfferForm formKey="synthetic" />); await walkToReview();
    fireEvent.click(screen.getByRole('button', { name: 'Verify request' })); fireEvent.click(screen.getByRole('button', { name: 'Request an offer' }));
    await screen.findByText(/We could not confirm your request/);
    expect(sessionStorage.length).toBe(1); first.unmount();
    render(<SellerOfferForm formKey="synthetic" />);
    await screen.findByRole('heading', { name: 'Step 4 of 4 · Review' });
    expect(screen.queryByRole('button', { name: 'Edit details' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Verify request' })); fireEvent.click(screen.getByRole('button', { name: 'Retry same request' }));
    await screen.findByRole('heading', { name: 'Your request is received' });
    expect(sent[1]).toEqual(sent[0]); expect(sessionStorage.length).toBe(0);
  });
  it('does not call submission or replace recovery when displayed wording changes', async () => {
    preserveSellerInquiry(sessionStorage, pending);
    fetcher.mockResolvedValue(response({ definition: { ...definition, version: 'v2' }, bot_site_key: 'public-key' }));
    render(<SellerOfferForm formKey="synthetic" />);
    await screen.findByText(/The form has changed/);
    expect(screen.queryByRole('button', { name: 'Verify request' })).not.toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(1); expect(sessionStorage.length).toBe(1);
  });
  it('never treats an unrelated receipt as confirmation', async () => {
    preserveSellerInquiry(sessionStorage, pending);
    fetcher.mockImplementation(async (_url, options) => options?.method === 'POST'
      ? response({ submission_id: 'fd000000-0000-4000-8000-000000000002', status: 'received', duplicate: false })
      : response({ definition, bot_site_key: 'public-key' }));
    render(<SellerOfferForm formKey="synthetic" />); await screen.findByRole('button', { name: 'Verify request' });
    fireEvent.click(screen.getByRole('button', { name: 'Verify request' })); fireEvent.click(screen.getByRole('button', { name: 'Retry same request' }));
    await screen.findByText(/We could not confirm your request/); expect(sessionStorage.length).toBe(1);
    expect(screen.queryByText('Your request is received')).not.toBeInTheDocument();
  });
  it('keeps corrupt saved input untouched and disables new submission', async () => {
    sessionStorage.setItem('hilltop.offer.pending:synthetic', 'broken');
    fetcher.mockResolvedValue(response({ definition, bot_site_key: 'public-key' }));
    render(<SellerOfferForm formKey="synthetic" />); await screen.findByText(/A saved request could not be read/);
    expect(screen.queryByRole('button', { name: 'Continue' })).not.toBeInTheDocument();
    expect(sessionStorage.getItem('hilltop.offer.pending:synthetic')).toBe('broken');
  });
  it('shows disabled availability without verification or a sign-in demand', async () => {
    fetcher.mockResolvedValue(response({}, 404)); render(<SellerOfferForm formKey="synthetic" />);
    await screen.findByText('This offer request form is not available right now.');
    expect(screen.queryByRole('button', { name: 'Verify request' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' })); await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  });
});
