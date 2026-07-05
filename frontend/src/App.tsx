import { Component, useEffect, useState } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { Session } from '@supabase/supabase-js';
import { supabase, initSupabase } from '@/lib/supabase';
import { Layout } from '@/components/layout/Layout';

// Auth pages (no Layout wrapper)
import { Login } from '@/pages/Login';
import { Register } from '@/pages/Register';

// Main app pages
import { Dashboard } from '@/pages/Dashboard';
import { Leads } from '@/pages/Leads';
import { Pipeline } from '@/pages/Pipeline';
import { DealAnalyzer } from '@/pages/DealAnalyzer';
import { Buyers } from '@/pages/Buyers';
import { AIAgents } from '@/pages/AIAgents';
import { Acquisitions } from '@/pages/Acquisitions';
import { Tasks } from '@/pages/Tasks';
import { Reports } from '@/pages/Reports';
import { SetupWizard } from '@/pages/SetupWizard';
import { UserManual } from '@/pages/UserManual';
import { LandLeads } from '@/pages/LandLeads';
import { BuyerIntelligence } from '@/pages/BuyerIntelligence';
import { LeadGenEngine } from '@/pages/LeadGenEngine';
import { MasterListBuilder } from '@/pages/MasterListBuilder';
import { LeadForm } from '@/pages/LeadForm';
import { FacebookAdsCommandCenter } from '@/pages/FacebookAdsCommandCenter';

// Admin pages
import { AdminUsers } from '@/pages/admin/Users';

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
          <p className="font-semibold text-gray-800 mb-2">Fix in Railway → Variables:</p>
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

export default function App() {
  // Start as 'ready' only when supabase.ts already pre-initialized from baked VITE_ vars.
  // Otherwise fetch config from /api/config at runtime (Railway env vars).
  const [configState, setConfigState] = useState<ConfigState>(
    supabase ? 'ready' : 'loading'
  );
  const [session, setSession] = useState<Session | null | undefined>(undefined);

  // Phase 1 — fetch runtime config when build-time vars weren't available
  useEffect(() => {
    if (configState !== 'loading') return;

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);

    fetch('/api/config', { signal: controller.signal })
      .then(r => { if (!r.ok) throw new Error(`config ${r.status}`); return r.json(); })
      .then(({ supabase_url, supabase_anon_key }: Record<string, string>) => {
        if (!supabase_url || !supabase_anon_key) throw new Error('empty');
        initSupabase(supabase_url, supabase_anon_key);
        setConfigState('ready');
      })
      .catch(() => setConfigState('error'))
      .finally(() => clearTimeout(timer));

    return () => { controller.abort(); clearTimeout(timer); };
  }, [configState]);

  // Phase 2 — init auth once Supabase client exists
  useEffect(() => {
    if (configState !== 'ready') return;

    // Hard fallback: if nothing resolves within 6 s, treat as unauthenticated.
    // This covers hung refresh-token calls and any unhandled rejection.
    const fallback = setTimeout(() => setSession(s => s === undefined ? null : s), 6000);

    supabase.auth
      .getSession()
      .then(({ data: { session } }) => {
        clearTimeout(fallback);
        setSession(session);
      })
      .catch(() => {
        clearTimeout(fallback);
        setSession(null);
      });

    // onAuthStateChange fires INITIAL_SESSION immediately (async microtask)
    // and subsequent LOGIN / LOGOUT / TOKEN_REFRESHED events.
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        clearTimeout(fallback);
        setSession(session);
      }
    );

    return () => {
      clearTimeout(fallback);
      subscription.unsubscribe();
    };
  }, [configState]);

  if (configState === 'error') return <ConfigError />;
  if (configState === 'loading' || session === undefined) return <Spinner />;

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            {!session ? (
              <>
                <Route path="/login"    element={<Login />} />
                <Route path="/register" element={<Register />} />
                <Route path="*"         element={<Navigate to="/login" replace />} />
              </>
            ) : (
              <>
                {/* Full-screen routes — no layout wrapper */}
                <Route path="/setup"        element={<SetupWizard />} />
                <Route path="/form/:formId" element={<LeadForm />} />

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
                  <Route path="/admin/users"  element={<AdminUsers />} />
                  <Route path="*"             element={<Navigate to="/" replace />} />
                </Route>
              </>
            )}
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
