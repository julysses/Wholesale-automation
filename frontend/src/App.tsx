import { useEffect, useState } from 'react';
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
import { LeadForm } from '@/pages/LeadForm';
import { FacebookAdsCommandCenter } from '@/pages/FacebookAdsCommandCenter';

// Admin pages
import { AdminUsers } from '@/pages/admin/Users';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 60000, retry: 1 },
  },
});

type ConfigState = 'loading' | 'ready' | 'error';

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
          The app could not connect to the database. Supabase credentials are missing.
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

export default function App() {
  const [configState, setConfigState] = useState<ConfigState>(
    // If build-time env vars were baked in, supabase.ts already initialized — skip fetch
    supabase ? 'ready' : 'loading'
  );
  const [session, setSession] = useState<Session | null | undefined>(undefined);

  // Phase 1: fetch runtime config from /api/config (runs when build-time vars missing)
  useEffect(() => {
    if (configState !== 'loading') return;

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);

    fetch('/api/config', { signal: controller.signal })
      .then(r => {
        if (!r.ok) throw new Error(`/api/config returned ${r.status}`);
        return r.json();
      })
      .then(({ supabase_url, supabase_anon_key }: { supabase_url: string; supabase_anon_key: string }) => {
        if (!supabase_url || !supabase_anon_key) throw new Error('empty config');
        initSupabase(supabase_url, supabase_anon_key);
        setConfigState('ready');
      })
      .catch(() => setConfigState('error'))
      .finally(() => clearTimeout(timeout));

    return () => { controller.abort(); clearTimeout(timeout); };
  }, [configState]);

  // Phase 2: auth init — only after Supabase client is ready
  useEffect(() => {
    if (configState !== 'ready') return;

    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
    });
    return () => subscription.unsubscribe();
  }, [configState]);

  if (configState === 'error') return <ConfigError />;
  if (configState === 'loading' || session === undefined) return <Spinner />;

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {!session ? (
            // ── Unauthenticated routes ────────────────────────────────────────
            <>
              <Route path="/login"    element={<Login />} />
              <Route path="/register" element={<Register />} />
              <Route path="*"         element={<Navigate to="/login" replace />} />
            </>
          ) : (
            // ── Authenticated routes ──────────────────────────────────────────
            <>
              {/* Full-screen routes — no layout wrapper */}
              <Route path="/setup" element={<SetupWizard />} />
              <Route path="/form/:formId" element={<LeadForm />} />

              {/* Main app with shared Layout (sidebar + topbar) */}
              <Route element={<Layout />}>
                <Route path="/"             element={<Dashboard />} />
                <Route path="/leads"        element={<Leads />} />
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
                {/* Admin routes — access enforced inside the page component */}
                <Route path="/admin/users"  element={<AdminUsers />} />
                <Route path="*"             element={<Navigate to="/" replace />} />
              </Route>
            </>
          )}
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
