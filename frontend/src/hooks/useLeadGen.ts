import { apiFetch } from '@/lib/api';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import type { AdCampaign, AdCreative, LeadFormConfig, LeadFormSubmission } from '@/types';

// ── Ad Campaigns ──────────────────────────────────────────────────────────────

export function useAdCampaigns() {
  return useQuery<AdCampaign[]>({
    queryKey: ['ad_campaigns'],
    queryFn: async () => {
      const resp = await supabase
        .from('ad_campaigns')
        .select('*')
        .order('created_at', { ascending: false });
      if (resp.error) throw resp.error;
      return resp.data || [];
    },
    staleTime: 30000,
  });
}

export function useUpdateCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, updates }: { id: string; updates: Partial<AdCampaign> }) => {
      const resp = await supabase.from('ad_campaigns').update(updates).eq('id', id).select().single();
      if (resp.error) throw resp.error;
      return resp.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ad_campaigns'] }),
  });
}

export function useCreateCampaign() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: Partial<AdCampaign>) => {
      const resp = await supabase.from('ad_campaigns').insert(data).select().single();
      if (resp.error) throw resp.error;
      return resp.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ad_campaigns'] }),
  });
}

// ── Ad Creatives ──────────────────────────────────────────────────────────────

export function useAdCreatives(campaignId?: string) {
  return useQuery<AdCreative[]>({
    queryKey: ['ad_creatives', campaignId],
    queryFn: async () => {
      let query = supabase
        .from('ad_creatives')
        .select('*')
        .order('created_at', { ascending: false });
      if (campaignId) query = query.eq('campaign_id', campaignId);
      const resp = await query;
      if (resp.error) throw resp.error;
      return resp.data || [];
    },
    enabled: true,
    staleTime: 30000,
  });
}

export function useUpdateCreative() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, updates }: { id: string; updates: Partial<AdCreative> }) => {
      const resp = await supabase.from('ad_creatives').update(updates).eq('id', id).select().single();
      if (resp.error) throw resp.error;
      return resp.data;
    },
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: ['ad_creatives'] });
    },
  });
}

export function useCreateCreative() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: Partial<AdCreative>) => {
      const resp = await supabase.from('ad_creatives').insert(data).select().single();
      if (resp.error) throw resp.error;
      return resp.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ad_creatives'] }),
  });
}

// ── Lead Form Configs ─────────────────────────────────────────────────────────

export function useLeadFormConfigs() {
  return useQuery<LeadFormConfig[]>({
    queryKey: ['lead_form_configs'],
    queryFn: async () => {
      const resp = await supabase
        .from('lead_form_configs')
        .select('*')
        .order('created_at', { ascending: false });
      if (resp.error) throw resp.error;
      return resp.data || [];
    },
    staleTime: 30000,
  });
}

export function useUpdateFormConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, updates }: { id: string; updates: Partial<LeadFormConfig> }) => {
      const resp = await supabase.from('lead_form_configs').update(updates).eq('id', id).select().single();
      if (resp.error) throw resp.error;
      return resp.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lead_form_configs'] }),
  });
}

export function useCreateFormConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: Partial<LeadFormConfig>) => {
      const resp = await supabase.from('lead_form_configs').insert(data).select().single();
      if (resp.error) throw resp.error;
      return resp.data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['lead_form_configs'] }),
  });
}

// ── Lead Form Submissions ─────────────────────────────────────────────────────

export function useLeadFormSubmissions(formId?: string) {
  return useQuery<LeadFormSubmission[]>({
    queryKey: ['lead_form_submissions', formId],
    queryFn: async () => {
      let query = supabase
        .from('lead_form_submissions')
        .select('*, lead_form_configs(name, slug)')
        .order('created_at', { ascending: false })
        .limit(100);
      if (formId) query = query.eq('form_id', formId);
      const resp = await query;
      if (resp.error) throw resp.error;
      return resp.data || [];
    },
    staleTime: 15000,
  });
}

// ── Lead Gen KPIs ─────────────────────────────────────────────────────────────

export interface LeadGenKPIs {
  leads_today: number;
  leads_week: number;
  hot_leads: number;
  avg_cpl: number;
  avg_lead_quality: number;
  total_spend: number;
  cost_per_contract_est: number;
}

export function useLeadGenKPIs() {
  return useQuery<LeadGenKPIs>({
    queryKey: ['lead_gen_kpis'],
    queryFn: async () => {
      const resp = await apiFetch('/api/lead-gen/kpis');
      if (!resp.ok) throw new Error('Failed to fetch KPIs');
      return resp.json();
    },
    staleTime: 30000,
    refetchInterval: 60000,
  });
}

// ── Inbound leads over time (for chart) ───────────────────────────────────────

export function useInboundLeadsTrend(days = 30) {
  return useQuery({
    queryKey: ['inbound_leads_trend', days],
    queryFn: async () => {
      const since = new Date();
      since.setDate(since.getDate() - days);
      const resp = await supabase
        .from('leads')
        .select('created_at, inbound_channel, source')
        .not('inbound_channel', 'is', null)
        .gte('created_at', since.toISOString())
        .order('created_at', { ascending: true });
      if (resp.error) throw resp.error;

      // Group by date
      const byDate: Record<string, { facebook: number; web_form: number; total: number }> = {};
      for (const lead of resp.data || []) {
        const date = lead.created_at.slice(0, 10);
        if (!byDate[date]) byDate[date] = { facebook: 0, web_form: 0, total: 0 };
        byDate[date].total++;
        if (lead.inbound_channel === 'facebook_lead_ad') byDate[date].facebook++;
        else byDate[date].web_form++;
      }

      return Object.entries(byDate)
        .map(([date, counts]) => ({ date, ...counts }))
        .sort((a, b) => a.date.localeCompare(b.date));
    },
    staleTime: 60000,
  });
}
