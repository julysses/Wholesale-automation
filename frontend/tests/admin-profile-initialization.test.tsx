import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  session: vi.fn(), profile: vi.fn(), users: vi.fn(),
  authCallback: undefined as ((event: string, session: { user: { id: string } } | null) => void) | undefined,
}));
vi.mock('@/lib/supabase', () => ({ supabase: {
  auth: {
    getSession: mocks.session,
    onAuthStateChange: (callback: typeof mocks.authCallback) => {
      mocks.authCallback = callback;
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    },
  },
  from: (table: string) => {
    if (table === 'my_profile') return { select: () => ({ single: mocks.profile }) };
    if (table === 'profiles') return { select: () => ({ order: mocks.users }) };
    throw new Error(`Unexpected table ${table}`);
  },
} }));
import { AdminUsers } from '@/pages/admin/Users';

const admin = {
  id: 'admin-1', role: 'admin', status: 'approved', email: 'admin@example.invalid',
  full_name: 'Approved Admin', avatar_url: null, created_at: '2026-09-01', approved_at: '2026-09-01',
};
type SessionResult = { data: { session: { user: { id: string } } | null } };
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
function showAdminPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>
    <MemoryRouter initialEntries={['/admin/users']}><Routes>
      <Route path="/admin/users" element={<AdminUsers />} />
      <Route path="/" element={<h1>Dashboard destination</h1>} />
    </Routes></MemoryRouter>
  </QueryClientProvider>);
}
beforeEach(() => {
  mocks.session.mockReset(); mocks.profile.mockReset(); mocks.users.mockReset();
  mocks.authCallback = undefined;
  mocks.session.mockResolvedValue({ data: { session: { user: { id: admin.id } } } });
  mocks.profile.mockResolvedValue({ data: admin, error: null });
  mocks.users.mockResolvedValue({ data: [], error: null });
});

it('keeps the real admin page mounted while initial session resolution is delayed', async () => {
  const session = deferred<SessionResult>();
  mocks.session.mockReturnValue(session.promise);
  showAdminPage();
  expect(screen.getByText('Loading...')).toBeInTheDocument();
  expect(screen.queryByText('Dashboard destination')).not.toBeInTheDocument();
  expect(mocks.profile).not.toHaveBeenCalled();
  expect(mocks.users).not.toHaveBeenCalled();
  await act(async () => session.resolve({ data: { session: { user: { id: admin.id } } } }));
  expect(await screen.findByRole('heading', { name: 'User Management' })).toBeInTheDocument();
  expect(screen.queryByText('Dashboard destination')).not.toBeInTheDocument();
  await waitFor(() => expect(mocks.users).toHaveBeenCalledOnce());
});

it('waits for the profile query after session initialization before deciding access', async () => {
  const profile = deferred<{ data: typeof admin; error: null }>();
  mocks.profile.mockReturnValue(profile.promise);
  showAdminPage();
  await waitFor(() => expect(mocks.profile).toHaveBeenCalledOnce());
  expect(screen.getByText('Loading...')).toBeInTheDocument();
  expect(screen.queryByText('Dashboard destination')).not.toBeInTheDocument();
  expect(mocks.users).not.toHaveBeenCalled();
  await act(async () => profile.resolve({ data: admin, error: null }));
  expect(await screen.findByRole('heading', { name: 'User Management' })).toBeInTheDocument();
});

it('redirects an approved regular user after resolution without fetching the admin list', async () => {
  const session = deferred<SessionResult>();
  mocks.session.mockReturnValue(session.promise);
  mocks.profile.mockResolvedValue({ data: { ...admin, role: 'user' }, error: null });
  showAdminPage();
  expect(screen.getByText('Loading...')).toBeInTheDocument();
  await act(async () => session.resolve({ data: { session: { user: { id: admin.id } } } }));
  expect(await screen.findByText('Dashboard destination')).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'User Management' })).not.toBeInTheDocument();
  expect(mocks.users).not.toHaveBeenCalled();
});

it('does not let a late initial session response overwrite a newer auth event', async () => {
  const session = deferred<SessionResult>();
  mocks.session.mockReturnValue(session.promise);
  showAdminPage();
  await act(async () => mocks.authCallback?.('SIGNED_IN', { user: { id: admin.id } }));
  expect(await screen.findByRole('heading', { name: 'User Management' })).toBeInTheDocument();
  await act(async () => session.resolve({ data: { session: null } }));
  expect(screen.getByRole('heading', { name: 'User Management' })).toBeInTheDocument();
  expect(screen.queryByText('Dashboard destination')).not.toBeInTheDocument();
});

it('shows a retryable profile error instead of treating it as nonadmin access', async () => {
  mocks.profile.mockResolvedValueOnce({ data: null, error: { message: 'Profile unavailable' } });
  showAdminPage();
  expect(await screen.findByRole('alert')).toHaveTextContent('could not verify your administrator access');
  expect(screen.queryByText('Dashboard destination')).not.toBeInTheDocument();
  expect(mocks.users).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Retry access check' }));
  expect(await screen.findByRole('heading', { name: 'User Management' })).toBeInTheDocument();
});

it('handles failed initial session reads without an unhandled rejection or admin fetch', async () => {
  mocks.session.mockRejectedValue(new Error('Session unavailable'));
  showAdminPage();
  expect(await screen.findByText('Dashboard destination')).toBeInTheDocument();
  expect(mocks.users).not.toHaveBeenCalled();
});
