import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import { LeadForm } from '@/pages/LeadForm';

function renderForm() {
  return render(<MemoryRouter initialEntries={['/form/hilltop-home-co']}>
    <Routes><Route path="/form/:formId" element={<LeadForm />} /></Routes>
  </MemoryRouter>);
}

it('recovers from a service outage through a read-only retry', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: false, status: 503 })
    .mockResolvedValueOnce({ ok: true, json: async () => ({
      id: 'test', headline: 'Request your offer', questions: [],
    }) });
  vi.stubGlobal('fetch', fetchMock);
  renderForm();
  expect(await screen.findByRole('alert')).toHaveTextContent('could not load');
  expect(screen.queryByText(/not found/i)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(await screen.findByText('Request your offer')).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  for (const [url, options] of fetchMock.mock.calls) {
    expect(url).toBe('/api/forms/hilltop-home-co');
    expect(options.method).toBeUndefined();
  }
});

it('distinguishes a missing form from a service outage', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404 }));
  renderForm();
  expect(await screen.findByRole('alert')).toHaveTextContent('not found or is no longer active');
});

it('ends the loading state when the config request stalls', async () => {
  vi.useFakeTimers();
  try {
    vi.stubGlobal('fetch', vi.fn((_url, { signal }) => new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    })));
    renderForm();
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(screen.getByRole('alert')).toHaveTextContent('connection is taking too long');
    expect(screen.getByRole('button', { name: 'Try again' })).toBeEnabled();
  } finally {
    vi.useRealTimers();
  }
});

it('uses a fresh verification token when retrying an unconfirmed inquiry', async () => {
  type WidgetOptions = { callback: (token: string) => void; action: string };
  const renderWidget = vi.fn<(container: HTMLElement, options: WidgetOptions) => string>().mockReturnValue('widget');
  vi.stubGlobal('turnstile', { render: renderWidget, remove: vi.fn() });
  const fetchMock = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({
      id: 'test', headline: 'Request your offer', slug: 'hilltop-home-co', questions: [],
      turnstile_site_key: 'public-widget-key',
    }) })
    .mockRejectedValueOnce(new TypeError('Connection lost after submission'))
    .mockImplementationOnce(async (_url, options) => {
      const payload = JSON.parse(options.body);
      return { ok: true, json: async () => ({
        success: true, submission_id: payload.request_id, processing_status: 'processed',
      }) };
    });
  vi.stubGlobal('fetch', fetchMock);
  try {
    renderForm();
    const submit = await screen.findByRole('button', { name: 'Get My Cash Offer' });
    expect(submit).toBeDisabled();
    const firstWidget = renderWidget.mock.calls[0][1];
    expect(firstWidget.action).toBe('hilltop-home-co');
    act(() => firstWidget.callback('first-token'));
    fireEvent.click(submit);
    const retry = await screen.findByRole('button', { name: 'Retry Saved Inquiry' });
    expect(retry).toBeDisabled();
    act(() => renderWidget.mock.calls[1][1].callback('fresh-token'));
    fireEvent.click(retry);
    expect(await screen.findByText("You're All Set!")).toBeInTheDocument();
    const first = JSON.parse(fetchMock.mock.calls[1][1].body);
    const second = JSON.parse(fetchMock.mock.calls[2][1].body);
    expect(first.turnstile_token).toBe('first-token');
    expect(second).toEqual({ ...first, turnstile_token: 'fresh-token' });
  } finally {
    sessionStorage.clear();
    vi.unstubAllGlobals();
  }
});
