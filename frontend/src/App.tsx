import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { Session } from '@supabase/supabase-js';
import { supabase } from '@/lib/supabase';
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

// Admin pages
import { AdminUsers } from '@/pages/admin/Users';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 60000, retry: 1 },
  },
});

export default function App() {
  const [session, setSession] = useState<Session | null | undefined>(undefined);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session);
    });
    const { data: { subscription } } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
    });
    return () => subscription.unsubscribe();
  }, []);

  // Loading state
  if (session === undefined) {
    return (
      <div className="min-h-screen bg-[#F2F4F6] flex items-center justify-center">
        <div className="h-8 w-8 border-4 border-[#1B3A5C] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

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
              {/* Setup wizard — full-screen, no layout wrapper */}
              <Route path="/setup" element={<SetupWizard />} />

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
