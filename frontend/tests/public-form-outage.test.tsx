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
