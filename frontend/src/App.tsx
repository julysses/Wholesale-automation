import { Component, Suspense, lazy, useEffect, useRef, useState } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import type { Session } from '@supabase/supabase-js';
import { supabase, initSupabase } from '@/lib/supabase';
import { useAutoScoreStore } from '@/stores/useAutoScoreStore';
import { useLeadStore } from '@/stores/useLeadStore';
import { useDealStore } from '@/stores/useDealStore';
import { Layout } from '@/components/layout/Layout';

// Auth pages (no Layout wrapper)
const Login = lazy(() => import('@/pages/Login').then(m => ({ default: m.Login })));
const Register = lazy(() => import('@/pages/Register').then(m => ({ default: m.Register })));

// Main app pages
const Dashboard = lazy(() => import('@/pages/Dashboard').then(m => ({ default: m.Dashboard })));
const Leads = lazy(() => import('@/pages/Leads').then(m => ({ default: m.Leads })));
const Pipeline = lazy(() => import('@/pages/Pipeline').then(m => ({ default: m.Pipeline })));
const DealAnalyzer = lazy(() => import('@/pages/DealAnalyzer').then(m => ({ default: m.DealAnalyzer })));
const Buyers = lazy(() => import('@/pages/Buyers').then(m => ({ default: m.Buyers })));
const AIAgents = lazy(() => import('@/pages/AIAgents').then(m => ({ default: m.AIAgents })));
const Acquisitions = lazy(() => import('@/pages/Acquisitions').then(m => ({ default: m.Acquisitions })));
const Tasks = lazy(() => import('@/pages/Tasks').then(m => ({ default: m.Tasks })));
const Reports = lazy(() => import('@/pages/Reports').then(m => ({ default: m.Reports })));
const SetupWizard = lazy(() => import('@/pages/SetupWizard').then(m => ({ default: m.SetupWizard })));
const UserManual = lazy(() => import('@/pages/UserManual').then(m => ({ default: m.UserManual })));
const LandLeads = lazy(() => import('@/pages/LandLeads').then(m => ({ default: m.LandLeads })));
const BuyerIntelligence = lazy(() => import('@/pages/BuyerIntelligence').then(m => ({ default: m.BuyerIntelligence })));
const LeadGenEngine = lazy(() => import('@/pages/LeadGenEngine').then(m => ({ default: m.LeadGenEngine })));
const MasterListBuilder = lazy(() => import('@/pages/MasterListBuilder').then(m => ({ default: m.MasterListBuilder })));
const LeadForm = lazy(() => import('@/pages/LeadForm').then(m => ({ default: m.LeadForm })));
const FacebookAdsCommandCenter = lazy(() => import('@/pages/FacebookAdsCommandCenter').then(m => ({ default: m.FacebookAdsCommandCenter })));

// Admin pages
const AdminUsers = lazy(() => import('@/pages/admin/Users').then(m => ({ default: m.AdminUsers })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 60000, retry: 1 },
  },
});

// ── Error Boundary ─────────────────────────────────────────────────────────────
// Catches render-time JS crashes that would otherwise show a blank screen
// in production (React silently unmounts the tree with no visible feedback).
class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[WholesaleOS] Render error:', error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      const msg = (this.state.error as Error).message;
      return (
        <div className="min-h-screen bg-[#F2F4F6] flex items-center justify-center p-6">
          <div className="bg-white rounded-2xl shadow-sm border border-red-100 max-w-lg w-full p-8 text-center space-y-4">
            <div className="h-12 w-12 bg-red-100 rounded-full flex items-center justify-center mx-auto">
              <span className="text-red-600 text-xl font-bold">!</span>
            </div>
            <h1 className="text-lg font-bold text-gray-900">Something went wrong</h1>
            <p className="text-sm text-gray-600">
              The app encountered an error and couldn't render. Check the browser console for details.
            </p>
            <pre className="bg-gray-50 rounded-lg p-3 text-xs text-left text-red-700 overflow-auto max-h-32">
              {msg}
            </pre>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 bg-[#1B3A5C] text-white text-sm rounded-lg hover:bg-[#1B3A5C]/90 transition-colors"
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

// ── UI helpers ─────────────────────────────────────────────────────────────────
function Spinner() {
  return (
    <div className="min-h-screen bg-[#F2F4F6] flex items-center justify-center">
      <div className="h-8 w-8 border-4 border-[#1B3A5C] border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

function ConfigError() {
  return (
    <div className="min-h-screen bg-[#F2F4F6] flex items-center justify-center p-6">
      <div className="bg-white rounded-2xl shadow-sm border border-red-100 max-w-md w-full p-8 text-center space-y-4">
        <div className="h-12 w-12 bg-red-100 rounded-full flex items-center justify-center mx-auto">
          <span className="text-red-600 text-xl font-bold">!</span>
        </div>
        <h1 className="text-lg font-bold text-gray-900">App Configuration Error</h1>
        <p className="text-sm text-gray-600">
          The app could not connect to the database. Supabase credentials are missing or invalid.
        </p>
        <div className="bg-gray-50 rounded-xl p-4 text-left text-xs font-mono space-y-1 text-gray-700">
          <p className="font-semibold text-gray-800 mb-2">Deployment configuration:</p>
          <p>VITE_SUPABASE_URL=https://xxx.supabase.co</p>
          <p>VITE_SUPABASE_ANON_KEY=eyJ...</p>
        </div>
        <p className="text-xs text-gray-400">
          Both values are in Supabase → Settings → API. After adding them, trigger a redeploy.
        </p>
        <button
          onClick={() => window.location.reload()}
          className="px-4 py-2 bg-[#1B3A5C] text-white text-sm rounded-lg hover:bg-[#1B3A5C]/90 transition-colors"
        >
          Retry
        </button>
      </div>
    </div>
  );
}

// ── Main App ───────────────────────────────────────────────────────────────────
type ConfigState = 'loading' | 'ready' | 'error';

function OperatorApp() {
  // Start as 'ready' only when supabase.ts already pre-initialized from baked VITE_ vars.
  // Otherwise fetch config from /api/config at runtime (Railway env vars).
  const [configState, setConfigState] = useState<ConfigState>(
    supabase ? 'ready' : 'loading'
  );
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const userId = useRef<string | null | undefined>(undefined);

  // Phase 1 — fetch runtime config when build-time vars weren't available
  useEffect(() => {
    if (configState !== 'loading') return;

    let active = true;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);

    fetch('/api/config', { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error(`config ${r.status}`); return r.json(); })
      .then(({ supabase_url, supabase_anon_key }: Record<string, string>) => {
        if (!active) return;
        if (!supabase_url || !supabase_anon_key) throw new Error('empty');
        initSupabase(supabase_url, supabase_anon_key);
        setConfigState('ready');
      })
      .catch(() => { if (active) setConfigState('error'); })
      .finally(() => clearTimeout(timer));

    return () => { active = false; controller.abort(); clearTimeout(timer); };
  }, [configState]);

  // Phase 2 — init auth once Supabase client exists
  useEffect(() => {
    if (configState !== 'ready') return;

    let active = true;
    const acceptSession = (next: Session | null) => {
      if (!active) return;
      const nextId = next?.user.id ?? null;
      if (userId.current !== nextId) {
        queryClient.clear();
        useAutoScoreStore.getState().cancel();
        useAutoScoreStore.getState().dismiss();
        useLeadStore.getState().setSelectedLead(null);
        useDealStore.getState().setDeals([]);
        userId.current = nextId;
      }
      setSession(next);
    };

    // Hard fallback: if nothing resolves within 6 s, treat as unauthenticated.
    // This covers hung refresh-token calls and any unhandled rejection.
    const fallback = setTimeout(() => setSession(s => s === undefined ? null : s), 6000);

    supabase.auth
      .getSession()
      .then(({ data: { session } }) => {
        clearTimeout(fallback);
        acceptSession(session);
      })
      .catch(() => {
        clearTimeout(fallback);
        acceptSession(null);
      });

    // onAuthStateChange fires INITIAL_SESSION immediately (async microtask)
    // and subsequent LOGIN / LOGOUT / TOKEN_REFRESHED events.
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        clearTimeout(fallback);
        acceptSession(session);
      }
    );

    return () => {
      active = false;
      clearTimeout(fallback);
      subscription.unsubscribe();
    };
  }, [configState]);

  if (configState === 'error') return <ConfigError />;
  if (configState === 'loading' || session === undefined) return <Spinner />;

  return (
    <Routes>
    {!session ? (
      <>
        <Route path="/login"    element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route path="*"         element={<Navigate to="/login" replace />} />
      </>
    ) : (
      <Route element={<ApprovalGate key={session.user.id} userId={session.user.id} />}>
        {/* Full-screen routes — no layout wrapper */}
        <Route element={<AdminGate userId={session.user.id} />}>
          <Route path="/setup" element={<SetupWizard />} />
          <Route path="/admin/users" element={<AdminUsers />} />
        </Route>

        {/* Main app with shared Layout (sidebar + topbar) */}
        <Route element={<Layout />}>
          <Route path="/"             element={<Dashboard />} />
          <Route path="/leads"        element={<Leads />} />
          <Route path="/master-list"  element={<MasterListBuilder />} />
          <Route path="/pipeline"     element={<Pipeline />} />
          <Route path="/analyzer"     element={<DealAnalyzer />} />
          <Route path="/buyers"       element={<Buyers />} />
          <Route path="/ai-agents"    element={<AIAgents />} />
          <Route path="/acquisitions" element={<Acquisitions />} />
          <Route path="/tasks"        element={<Tasks />} />
          <Route path="/reports"      element={<Reports />} />
          <Route path="/manual"       element={<UserManual />} />
          <Route path="/land"         element={<LandLeads />} />
          <Route path="/buyer-intel"  element={<BuyerIntelligence />} />
          <Route path="/lead-gen"     element={<LeadGenEngine />} />
          <Route path="/fb-ads"       element={<FacebookAdsCommandCenter />} />
          <Route path="*"             element={<Navigate to="/" replace />} />
        </Route>
      </Route>
    )}
    </Routes>
  );
}


function useAccessProfile(userId: string) {
  return useQuery({
    queryKey: ['access-profile', userId],
    queryFn: async () => {
      const { data, error } = await supabase.from('my_profile').select('status,role').single();
      if (error) throw error;
      return data as { status: string; role: string };
    },
    staleTime: 0,
    refetchInterval: 30000,
  });
}

function ApprovalGate({ userId }: { userId: string }) {
  const profile = useAccessProfile(userId);
  if (profile.isPending) return <Spinner />;
  if (profile.isError || profile.data?.status !== 'approved') {
    const message = profile.isError ? 'We could not verify your access. Please retry.'
      : profile.data?.status === 'pending' ? 'Your account is awaiting administrator approval.'
      : 'Your account does not currently have access. Contact your administrator.';
    return <div className="min-h-screen flex items-center justify-center bg-[#F2F4F6] p-6">
      <div className="max-w-md rounded-2xl border bg-white p-8 space-y-4 text-center">
        <h1 className="text-xl font-semibold">Account access</h1>
        <p>{message}</p>
        <button className="px-4 py-2 underline" onClick={() => profile.refetch()}>Check again</button>
        <button className="px-4 py-2 underline" onClick={() => supabase.auth.signOut()}>Sign out</button>
      </div>
    </div>;
  }
  return <Outlet />;
}

function AdminGate({ userId }: { userId: string }) {
  const { data } = useAccessProfile(userId);
  return data?.role === 'admin' ? <Outlet /> : <Navigate to="/" replace />;
}

export default function App() {
  return <ErrorBoundary>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<Spinner />}>
          <Routes>
            <Route path="/form/:formId" element={<LeadForm />} />
            <Route path="*" element={<OperatorApp />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  </ErrorBoundary>;
}
