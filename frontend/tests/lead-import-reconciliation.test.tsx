import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ api: vi.fn(), from: vi.fn(), rows: [] as string[][] }));
vi.mock('@/lib/api', () => ({ apiFetch: mocks.api }));
vi.mock('@/lib/supabase', () => ({ supabase: { from: mocks.from } }));
vi.mock('@/hooks/useLeads', async original => ({
  ...await original<typeof import('@/hooks/useLeads')>(),
  useLeads: () => ({data: {data: [], count: 0}, isLoading: false, error: null}),
}));
vi.mock('@/lib/parseFile', () => ({isSupportedFile: () => true, parseSpreadsheet: async () => mocks.rows}));
vi.mock('sonner', () => ({toast: {success: vi.fn(), error: vi.fn()}}));
import { Leads } from '@/pages/Leads';
beforeEach(() => { vi.clearAllMocks(); mocks.rows=[['Address','City','Phone'],['123 Test St','Dallas','2145550123']]; mocks.api.mockImplementation(async (path: string, init: RequestInit) => {
  if (path.includes('map')) throw new Error('Use offline mapping');
  const body = JSON.parse(init.body as string);
  return new Response(JSON.stringify({status: 'ok', request_id: body.request_id, replayed: false, imported: 0, updated: 1, skipped: 0, scored: 0, consolidated_rows: 1, owner_review: 0, scoring_state: 'completed'}));
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

it('explicit retry reuses the exact import reference and prepared body', async () => {
  mocks.api.mockRejectedValueOnce(new Error('Use offline mapping')).mockRejectedValueOnce(new Error('Saved response lost'));
  await upload();
  expect(await screen.findByRole('alert')).toHaveTextContent('Saved response lost');
  expect(mocks.api.mock.calls.filter(([path]) => path === '/api/ai/import-master-list')).toHaveLength(1);
  fireEvent.click(screen.getByRole('button', {name: 'Retry original import'}));
  expect(await screen.findByText(/1 existing leads reconciled/)).toBeInTheDocument();
  const attempts = mocks.api.mock.calls.filter(([path]) => path === '/api/ai/import-master-list');
  expect(attempts).toHaveLength(2);
  expect(attempts[0][1].body).toEqual(attempts[1][1].body);
  expect(JSON.parse(attempts[0][1].body).request_id).toMatch(/^[0-9a-f-]{36}$/);
});
it('rejects an otherwise successful response for another import reference', async () => {
  mocks.api.mockImplementation(async (path: string) => {
    if (path.includes('map')) throw new Error('Offline');
    return new Response(JSON.stringify({status:'ok',request_id:'different',imported:1,updated:0}));
  });
  await upload();
  expect(await screen.findByRole('alert')).toHaveTextContent('did not confirm this import reference');
  expect(mocks.api.mock.calls.filter(([path]) => path === '/api/ai/import-master-list')).toHaveLength(1);
});
it('keeps confirmed saves visible when scoring or ownership needs review', async () => {
  mocks.api.mockImplementation(async (path: string, init: RequestInit) => {
    if (path.includes('map')) throw new Error('Offline');
    const body=JSON.parse(init.body as string);
    return new Response(JSON.stringify({status:'ok',request_id:body.request_id,replayed:false,imported:1,updated:0,
      skipped:0,scored:0,consolidated_rows:1,owner_review:0,scoring_state:'review',warning:'Leads saved. Scoring needs review.'}));
  });
  await upload();
  expect(await screen.findByText('1 leads imported')).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('Scoring needs review');
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('passes negative numeric source text unchanged for server validation', async () => {
  mocks.rows=[['Address','City','Asking Price'],['123 Test St','Dallas','-$200']];
  await upload();
  expect(await screen.findByText(/1 existing leads reconciled/)).toBeInTheDocument();
  const call=mocks.api.mock.calls.find(([path])=>path==='/api/ai/import-master-list')!;
  expect(JSON.parse(call[1].body).rows[0].asking_price).toBe('-$200');
});
