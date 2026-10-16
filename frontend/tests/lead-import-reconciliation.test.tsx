import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ api: vi.fn(), from: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.api }));
vi.mock('@/lib/supabase', () => ({ supabase: { from: mocks.from } }));
vi.mock('@/hooks/useLeads', async original => ({
  ...await original<typeof import('@/hooks/useLeads')>(),
  useLeads: () => ({data: {data: [], count: 0}, isLoading: false, error: null}),
}));
vi.mock('@/lib/parseFile', () => ({isSupportedFile: () => true, parseSpreadsheet: async () => [
  ['Address', 'City', 'Phone'], ['123 Test St', 'Dallas', '2145550123'],
]}));
vi.mock('sonner', () => ({toast: {success: vi.fn(), error: vi.fn()}}));
import { Leads } from '@/pages/Leads';
beforeEach(() => { vi.clearAllMocks(); mocks.api.mockImplementation(async (path: string) => {
  if (path.includes('map')) throw new Error('Use offline mapping');
  return new Response(JSON.stringify({status: 'ok', imported: 0, updated: 1, skipped: 0}));
}); });
async function upload() {
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><Leads /></MemoryRouter></QueryClientProvider>);
  fireEvent.click(screen.getByRole('button', {name: /Import/}));
  fireEvent.change(document.querySelector('#csv-input')!, {target: {files: [new File(['test'], 'test.csv', {type:'text/csv'})]}});
  await waitFor(() => expect(screen.getByRole('button', {name: /Import.*lead/i})).toBeEnabled());
  fireEvent.click(screen.getByRole('button', {name: /Import.*lead/i}));
}
it('routes a repeat upload through reconciliation without direct database inserts', async () => {
  await upload();
  expect(await screen.findByText(/1 existing leads reconciled/)).toBeInTheDocument();
  const call = mocks.api.mock.calls.find(([path]) => path === '/api/ai/import-master-list')!;
  expect(JSON.parse(call[1].body)).toMatchObject({engine: 'rules', rows: [{property_address:'123 Test St',city:'Dallas',owner_phone_1:'2145550123'}]});
  expect(mocks.from).not.toHaveBeenCalled();
});
it('surfaces an ambiguous import failure and never automatically retries', async () => {
  mocks.api.mockRejectedValue(new Error('Connection lost; outcome unconfirmed'));
  await upload();
  expect(await screen.findByRole('alert')).toHaveTextContent('Connection lost; outcome unconfirmed');
  expect(mocks.api.mock.calls.filter(([path]) => path === '/api/ai/import-master-list')).toHaveLength(1);
  expect(mocks.from).not.toHaveBeenCalled();
});
