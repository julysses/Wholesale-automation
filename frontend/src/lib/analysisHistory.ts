import { supabase } from '@/lib/supabase';
import { queryByIds } from '@/lib/queryAll';

export const ANALYSIS_PAGE_SIZE = 50;
export async function loadAnalysisPage<T extends { id: string; lead_id: string | null }>(page: number) {
  const { data, error, count } = await supabase.from('deal_analyses')
    .select('*', { count: 'exact' })
    .order('analyzed_at', { ascending: false }).order('id', { ascending: false })
    .range((page - 1) * ANALYSIS_PAGE_SIZE, page * ANALYSIS_PAGE_SIZE - 1);
  if (error) throw error;
  if (!data || count === null) throw new Error('Analysis history could not be confirmed');
  const analyses = data as T[];
  const leads = await queryByIds<{ id: string; property_address: string; owner_first_name: string | null; owner_last_name: string | null }>(
    analyses.flatMap(row => row.lead_id ? [row.lead_id] : []),
    (ids, from, to) => supabase.from('leads').select('id,property_address,owner_first_name,owner_last_name')
      .in('id', ids).order('id').range(from, to),
  );
  const byId = new Map(leads.map(lead => [lead.id, lead]));
  return { count, data: analyses.map(row => {
    const lead = row.lead_id ? byId.get(row.lead_id) : undefined;
    return { ...row, property_address: lead?.property_address,
      owner_name: lead ? `${lead.owner_first_name ?? ''} ${lead.owner_last_name ?? ''}`.trim() : undefined };
  }) };
}
