import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { LeadForm } from '@/pages/LeadForm';
import { publicIntakeKey, readPublicIntake } from '@/lib/publicIntakeRecovery';

const form = { id: 'form-db-id', slug: 'test-form', name: 'QA', headline: 'QA inquiry', brand_color: '#123456', thank_you_message: 'Received by our team', questions: [
  { id: 'name', step: 1, type: 'text', field_name: 'first_name', label: 'First name', placeholder: 'First name', required: true },
  { id: 'sms', step: 2, type: 'checkbox', field_name: 'sms_opt_in', label: 'Optional original SMS disclosure', required: false },
] };
const response = (data: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => data });
function mount() {
  return render(<MemoryRouter initialEntries={['/form/test-form?utm_source=original&utm_campaign=qa']}><Routes><Route path="/form/:formId" element={<LeadForm />} /></Routes></MemoryRouter>);
}
async function fill() {
  fireEvent.change(await screen.findByPlaceholderText('First name'), { target: { value: 'Controlled original' } });
  fireEvent.click(screen.getByRole('button', { name: 'Next' }));
  fireEvent.click(screen.getByRole('checkbox'));
}
beforeEach(() => { sessionStorage.clear(); window.scrollTo = vi.fn(); window.history.replaceState({}, '', '/form/test-form?utm_source=original&utm_campaign=qa'); });

describe('public CRM inquiry recovery', () => {
  it('saves before dispatch, restores locked original answers and retries exact payload after lost acknowledgement', async () => {
    const sent: Record<string, unknown>[] = [];
    let succeed = false;
    vi.stubGlobal('fetch', vi.fn(async (_url, options) => {
      if (!options?.method) return response(form);
      const payload = JSON.parse(options.body);
      expect(readPublicIntake(sessionStorage, 'test-form')?.payload).toEqual(payload);
      sent.push(payload);
      if (!succeed) throw new TypeError('Lost acknowledgement');
      return response({ success: true, submission_id: payload.request_id, processing_status: 'processed' });
    }));
    const first = mount(); await fill();
    const submit = screen.getByRole('button', { name: 'Get My Cash Offer' });
    fireEvent.click(submit); fireEvent.click(submit);
    await screen.findByRole('button', { name: 'Retry Saved Inquiry' });
    expect(sent).toHaveLength(1);
    expect(sent[0]).toMatchObject({ answers: { first_name: 'Controlled original', sms_opt_in: 'true', sms_consent_text: 'Optional original SMS disclosure' }, utm_source: 'original', utm_campaign: 'qa' });
    first.unmount();
    window.history.replaceState({}, '', '/form/test-form?utm_source=changed');
    mount();
    expect(await screen.findByPlaceholderText('First name')).toHaveValue('Controlled original');
    expect(screen.getByPlaceholderText('First name')).toBeDisabled();
    succeed = true;
    fireEvent.click(screen.getByRole('button', { name: 'Retry Saved Inquiry' }));
    await screen.findByText("You're All Set!");
    expect(sent).toHaveLength(2); expect(sent[1]).toEqual(sent[0]);
    expect(sessionStorage.getItem(publicIntakeKey('test-form'))).toBeNull();
  });

  it.each([
    { success: true, submission_id: 'another-reference', processing_status: 'processed' },
    { success: true, processing_status: 'pending' },
    { success: false },
  ])('never confirms an HTTP 200 with an unfinished or wrong receipt', async result => {
    vi.stubGlobal('fetch', vi.fn(async (_url, options) => response(options?.method ? result : form)));
    mount(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Get My Cash Offer' }));
    await screen.findByRole('button', { name: 'Retry Saved Inquiry' });
    expect(screen.queryByText("You're All Set!")).not.toBeInTheDocument();
    expect(readPublicIntake(sessionStorage, 'test-form')).not.toBeNull();
    expect(screen.getByRole('checkbox')).toBeDisabled();
  });

  it('releases a first pre-write validation rejection but preserves a later uncertain retry rejection', async () => {
    let status = 422;
    vi.stubGlobal('fetch', vi.fn(async (_url, options) => response(options?.method ? { detail: 'Check details' } : form, options?.method ? status : 200)));
    mount(); await fill(); fireEvent.click(screen.getByRole('button', { name: 'Get My Cash Offer' }));
    await screen.findByText('Check details');
    expect(readPublicIntake(sessionStorage, 'test-form')).toBeNull();
    expect(screen.getByRole('checkbox')).toBeEnabled();
    status = 503; fireEvent.click(screen.getByRole('button', { name: 'Get My Cash Offer' }));
    await screen.findByRole('button', { name: 'Retry Saved Inquiry' });
    const reference = readPublicIntake(sessionStorage, 'test-form')?.payload.request_id;
    status = 422; fireEvent.click(screen.getByRole('button', { name: 'Retry Saved Inquiry' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Retry Saved Inquiry' })).toBeEnabled());
    expect(readPublicIntake(sessionStorage, 'test-form')?.payload.request_id).toBe(reference);
    expect(screen.getByRole('checkbox')).toBeDisabled();
  });

  it('malformed saved data prevents a new inquiry from dispatching', async () => {
    sessionStorage.setItem(publicIntakeKey('test-form'), '');
    const fetch = vi.fn(async () => response(form)); vi.stubGlobal('fetch', fetch);
    mount();
    expect(await screen.findByPlaceholderText('First name')).toBeDisabled();
    expect(await screen.findByRole('alert')).toHaveTextContent('cannot recover');
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('storage failure prevents provider-facing submission', async () => {
    const fetch = vi.fn(async () => response(form)); vi.stubGlobal('fetch', fetch);
    mount(); await fill();
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Unavailable'); });
    fireEvent.click(screen.getByRole('button', { name: 'Get My Cash Offer' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('cannot safely save');
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('optional unchecked SMS consent remains off and no failure warning appears while saving', async () => {
    let finish: (value: unknown) => void = () => {};
    let sent: Record<string, unknown> = {};
    vi.stubGlobal('fetch', vi.fn(async (_url, options) => {
      if (!options?.method) return response(form);
      sent = JSON.parse(options.body);
      return new Promise(resolve => { finish = resolve; });
    }));
    mount();
    fireEvent.change(await screen.findByPlaceholderText('First name'), { target: { value: 'QA no SMS' } });
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    fireEvent.click(screen.getByRole('button', { name: 'Get My Cash Offer' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect((sent.answers as Record<string,string>).sms_opt_in).toBeUndefined();
    finish(response({ success: true, submission_id: sent.request_id, processing_status: 'processed' }));
    await screen.findByText("You're All Set!");
  });
});
