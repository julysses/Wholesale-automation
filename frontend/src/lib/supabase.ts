import { createClient, SupabaseClient } from '@supabase/supabase-js';

// Live binding — all importers see the updated client after initSupabase() is called.
// Do NOT pre-initialize with placeholder values; an invalid client causes auth to hang.
export let supabase: SupabaseClient = null!;

export function initSupabase(url: string, anonKey: string): void {
  supabase = createClient(url, anonKey, {
    auth: { autoRefreshToken: true, persistSession: true },
    realtime: { params: { eventsPerSecond: 10 } },
  });
}

// Pre-initialize from build-time env vars when available (local dev / Docker).
// On Railway with nixpacks the VITE_ vars are typically empty; App.tsx fetches
// them at runtime from /api/config instead.
const _bakeUrl = import.meta.env.VITE_SUPABASE_URL as string;
const _bakeKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string;
if (_bakeUrl && _bakeKey) {
  try { initSupabase(_bakeUrl.trim(), _bakeKey.trim()); }
  catch { /* Runtime configuration can recover from invalid build-time values. */ }
}
