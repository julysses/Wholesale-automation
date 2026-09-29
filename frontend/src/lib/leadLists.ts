import { supabase } from '@/lib/supabase';
import { apiFetch } from '@/lib/api';

export interface LeadList {
  id: string;
  name: string;
  filename: string | null;
  created_at: string;
  row_count: number;
  lead_count: number;
  unscored: number;
  deletable_count: number;
  worked_count: number;
}

export interface BuyerImport {
  id: string;
  created_at: string;
  filename: string | null;
  market: string | null;
  status: string;
  buyers_remaining: number;
}

/** Register an uploaded file as a list so all of its leads can be reviewed or deleted together. */
export async function createLeadList(filename: string, rowCount: number): Promise<string | null> {
  const name = filename.replace(/\.[^.]+$/, '').slice(0, 120) || 'Uploaded list';
  const { data, error } = await supabase
    .from('lead_lists')
    .insert({ name, filename: filename.slice(0, 200), row_count: rowCount })
    .select('id')
    .single();
  // Lists are an organizing aid; never block an import because list tracking failed.
  return error || !data ? null : (data.id as string);
}

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return (await apiFetch(path, init)).json() as Promise<T>;
}

export const fetchLeadLists = () => json<{ lists: LeadList[] }>('/api/lead-lists').then(r => r.lists);
export const deleteLeadList = (id: string, includeWorked: boolean) =>
  json<{ deleted: number; kept_worked: number; list_removed: boolean }>(
    `/api/lead-lists/${encodeURIComponent(id)}?include_worked=${includeWorked}`, { method: 'DELETE' });
export const rescoreLeadList = (id: string) =>
  json<{ processed: number; scored: number }>(`/api/lead-lists/${encodeURIComponent(id)}/rescore`, { method: 'POST' });

export const fetchBuyerImports = () => json<{ imports: BuyerImport[] }>('/api/buyers/imports').then(r => r.imports);
export const deleteBuyerImport = (id: string) =>
  json<{ buyers_deleted: number }>(`/api/buyers/imports/${encodeURIComponent(id)}`, { method: 'DELETE' });

export interface CleanupRule {
  id: string;
  label: string;
  action: string;
  timeframe: string;
  why: string;
  count: number;
}
export interface HoldPolicy { who: string; keep: string; why: string }

export const fetchCleanupSuggestions = () =>
  json<{ rules: CleanupRule[]; hold: HoldPolicy[] }>('/api/lead-lists/cleanup-suggestions');
export const applyCleanup = (rule: string) =>
  json<{ deleted: number; failed: number }>(`/api/lead-lists/cleanup/${encodeURIComponent(rule)}`, { method: 'POST' });
