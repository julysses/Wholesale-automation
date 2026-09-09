import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { Buyer } from '@/types';

const mocks = vi.hoisted(() => ({ create: vi.fn(), update: vi.fn(), refetch: vi.fn(), error: null as Error | null }));
const buyers = [
  { id: 'buyer-1', first_name: 'Ana', last_name: 'Lopez', tier: 'A', target_zips: ['75201'], notes: 'Existing notes', strategy: ['fix_flip'] },
  { id: 'buyer-2', first_name: 'Ben', last_name: 'Jones', tier: 'B', target_zips: ['77001'], notes: 'Second buyer' },
] as Buyer[];
vi.mock('@/hooks/useBuyers', () => ({
  useBuyers: () => ({ data: buyers, isLoading: false, error: mocks.error, refetch: mocks.refetch }),
  useCreateBuyer: () => ({ mutateAsync: mocks.create, isPending: false }),
  useUpdateBuyer: () => ({ mutateAsync: mocks.update, isPending: false }),
  useDeleteBuyer: () => ({ mutate: vi.fn() }),
}));
vi.mock('@/hooks/useDeals', () => ({ useDeals: () => ({ data: [] }) }));
vi.mock('@/hooks/useAIAgent', () => ({ useBuyerMatcher: () => ({ match: vi.fn() }) }));
import { Buyers } from '@/pages/Buyers';

beforeEach(() => {
  vi.clearAllMocks();
  mocks.error = null;
  mocks.create.mockResolvedValue({});
  mocks.update.mockResolvedValue({});
});

function edit(name: string) {
  fireEvent.click(screen.getByRole('button', { name: `Actions for ${name}` }));
  fireEvent.click(screen.getByRole('button', { name: 'Edit', exact: true }));
}

it('loads each selected buyer and starts a fresh add form after editing', () => {
  render(<Buyers />);
  edit('Ana Lopez');
  expect(screen.getByLabelText('First Name *')).toHaveValue('Ana');
  expect(screen.getByLabelText('Target Zip Codes (comma-separated)')).toHaveValue('75201');
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  edit('Ben Jones');
  expect(screen.getByLabelText('First Name *')).toHaveValue('Ben');
  expect(screen.getByLabelText('Notes')).toHaveValue('Second buyer');
  fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
  fireEvent.click(screen.getByRole('button', { name: 'Add Buyer', exact: true }));
  expect(screen.getByLabelText('First Name *')).toHaveValue('');
  expect(screen.getByLabelText('Target Zip Codes (comma-separated)')).toHaveValue('');
});

it('creates buyers with schema fields and converts the zip input to an array', async () => {
  render(<Buyers />);
  fireEvent.click(screen.getByRole('button', { name: 'Add Buyer', exact: true }));
  fireEvent.change(screen.getByLabelText('First Name *'), { target: { value: ' Carla ' } });
  fireEvent.change(screen.getByLabelText('Last Name *'), { target: { value: ' Smith ' } });
  fireEvent.change(screen.getByLabelText('Target Zip Codes (comma-separated)'), { target: { value: '75201, 75202' } });
  fireEvent.submit(screen.getByLabelText('First Name *').closest('form')!);
  await waitFor(() => expect(mocks.create).toHaveBeenCalled());
  expect(mocks.create.mock.calls[0][0]).toMatchObject({ first_name: 'Carla', last_name: 'Smith', target_zips: ['75201', '75202'] });
  expect(mocks.create.mock.calls[0][0]).not.toHaveProperty('target_zips_str');
  await waitFor(() => expect(screen.queryByLabelText('First Name *')).not.toBeInTheDocument());
});

it('retains existing buyer fields in updates and keeps rejected saves open for retry', async () => {
  mocks.update.mockRejectedValueOnce(new Error('Database unavailable'));
  render(<Buyers />);
  edit('Ana Lopez');
  fireEvent.change(screen.getByLabelText('Company'), { target: { value: 'New Company' } });
  fireEvent.submit(screen.getByLabelText('First Name *').closest('form')!);
  await waitFor(() => expect(mocks.update).toHaveBeenCalledTimes(1));
  expect(mocks.update.mock.calls[0][0]).toMatchObject({ id: 'buyer-1', updates: { first_name: 'Ana', notes: 'Existing notes', company: 'New Company' } });
  expect(mocks.update.mock.calls[0][0].updates).not.toHaveProperty('target_zips_str');
  expect(screen.getByLabelText('Company')).toHaveValue('New Company');
  fireEvent.submit(screen.getByLabelText('First Name *').closest('form')!);
  await waitFor(() => expect(screen.queryByLabelText('Company')).not.toBeInTheDocument());
});

it('renders database failures with retry instead of an empty buyer state', () => {
  mocks.error = new Error('Connection unavailable');
  render(<Buyers />);
  expect(screen.getByRole('alert')).toHaveTextContent('Unable to load buyers: Connection unavailable');
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
  expect(mocks.refetch).toHaveBeenCalled();
  expect(screen.queryByText('No buyers found')).not.toBeInTheDocument();
});
