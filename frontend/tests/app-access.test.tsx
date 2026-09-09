import { StrictMode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';

const state = vi.hoisted(() => ({
  client: null as unknown,
  profile: { status: 'approved', role: 'user' },
  session: null as unknown,
}));
const client = {
  auth: {
    getSession: vi.fn(async () => ({ data: { session: state.session } })),
    onAuthStateChange: vi.fn(() => ({ data: { subscription: { unsubscribe: vi.fn() } } })),
    signOut: vi.fn(),
  },
  from: vi.fn(() => ({ select: () => ({ single: async () => ({ data: state.profile, error: null }) }) })),
};
vi.mock('@/lib/supabase', () => ({
  get supabase() { return state.client; },
  initSupabase: () => { state.client = client; },
}));
vi.mock('@/components/layout/Layout', async () => {
  const { Outlet } = await import('react-router-dom');
  return { Layout: () => <Outlet /> };
});
vi.mock('@/pages/Dashboard', () => ({ Dashboard: () => <h1>Dashboard test</h1> }));
vi.mock('@/pages/Login', () => ({ Login: () => <h1>Sign in test</h1> }));
vi.mock('@/pages/admin/Users', () => ({ AdminUsers: () => <h1>Admin users route</h1> }));
vi.mock('@/pages/SetupWizard', () => ({ SetupWizard: () => <h1>Admin setup route</h1> }));
import App from '@/App';

beforeEach(() => {
  state.client = null;
  state.session = null;
  state.profile = { status: 'approved', role: 'user' };
  window.history.replaceState({}, '', '/');
});

it('loads a public seller form without config or authentication', async () => {
  window.history.replaceState({}, '', '/form/hilltop-home-co');
  const fetcher = vi.fn(async () => new Response(JSON.stringify({
    id: 'form-1', headline: 'Request your cash offer', questions: [
      { id: 'consent', step: 1, type: 'checkbox', field_name: 'sms_opt_in', label: 'Agree to texts', required: true },
    ],
  })));
  vi.stubGlobal('fetch', fetcher);
  render(<App />);
  expect(await screen.findByText('Request your cash offer')).toBeInTheDocument();
  expect(window.location.pathname).toBe('/form/hilltop-home-co');
  expect(fetcher.mock.calls.every(args => String(args[0]).startsWith('/api/forms/'))).toBe(true);
  const checkbox = screen.getByRole('checkbox');
  fireEvent.click(checkbox); fireEvent.click(checkbox);
  fireEvent.click(screen.getByRole('button', { name: /offer|submit/i }));
  expect(await screen.findByText('This field is required')).toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it.each(['pending', 'suspended', 'denied'])('blocks a persisted %s session before dashboard render', async status => {
  state.client = client;
  state.session = { user: { id: 'test-user' }, access_token: 'test-token' };
  state.profile = { status, role: 'user' };
  render(<App />);
  expect(await screen.findByText('Account access')).toBeInTheDocument();
  expect(screen.queryByText('Dashboard test')).not.toBeInTheDocument();
});

it('allows an approved session to render the dashboard', async () => {
  state.client = client;
  state.session = { user: { id: 'test-user' }, access_token: 'test-token' };
  render(<App />);
  expect(await screen.findByText('Dashboard test')).toBeInTheDocument();
});

it('does not turn StrictMode cleanup into a configuration error', async () => {
  let calls = 0;
  vi.stubGlobal('fetch', vi.fn((_url, init) => {
    calls++;
    if (calls === 1) return new Promise((_resolve, reject) => {
      init.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    });
    return Promise.resolve(new Response(JSON.stringify({ supabase_url: 'https://test.supabase.co', supabase_anon_key: 'test' })));
  }));
  render(<StrictMode><App /></StrictMode>);
  await waitFor(() => expect(screen.getByText('Sign in test')).toBeInTheDocument());
  expect(screen.queryByText('App Configuration Error')).not.toBeInTheDocument();
});


it.each(['/admin/users', '/setup'])('rejects approved regular users from %s', async path => {
  state.client = client;
  state.session = { user: { id: 'regular-route-user' }, access_token: 'test-token' };
  state.profile = { status: 'approved', role: 'user' };
  window.history.replaceState({}, '', path);
  render(<App />);
  expect(await screen.findByText('Dashboard test')).toBeInTheDocument();
  expect(window.location.pathname).toBe('/');
  expect(screen.queryByText('Admin users route')).not.toBeInTheDocument();
  expect(screen.queryByText('Admin setup route')).not.toBeInTheDocument();
});

it.each([['/admin/users', 'Admin users route'], ['/setup', 'Admin setup route']])('allows approved administrators on %s', async (path, heading) => {
  state.client = client;
  state.session = { user: { id: 'admin-route-user' }, access_token: 'test-token' };
  state.profile = { status: 'approved', role: 'admin' };
  window.history.replaceState({}, '', path);
  render(<App />);
  expect(await screen.findByText(heading)).toBeInTheDocument();
  expect(window.location.pathname).toBe(path);
});
