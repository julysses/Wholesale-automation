import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import type { Lead } from '@/types';
import { toast } from 'sonner';

interface LeadsFilter {
  status?: string;
  source?: string;
  search?: string;
  page?: number;
  pageSize?: number;
}

export function useLeads(filters: LeadsFilter = {}) {
  const { status, source, search, page = 1, pageSize = 50 } = filters;

  return useQuery({
    queryKey: ['leads', filters],
    queryFn: async () => {
      let query = supabase
        .from('leads')
        .select('*', { count: 'exact' })
        .order('created_at', { ascending: false })
        .range((page - 1) * pageSize, page * pageSize - 1);

      if (status) query = query.eq('status', status);
      if (source) query = query.eq('source', source);
      if (search) {
        query = query.or(
          `property_address.ilike.%${search}%,owner_first_name.ilike.%${search}%,owner_last_name.ilike.%${search}%,owner_phone_1.ilike.%${search}%`
        );
      }

      const { data, error, count } = await query;
      if (error) throw error;
      return { data: data as Lead[], count: count ?? 0 };
    },
    staleTime: 60000,
  });
}

export function useHotLeads() {
  return useQuery({
    queryKey: ['leads', 'hot'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('leads')
        .select('*')
        .gte('total_score', 13)
        .order('total_score', { ascending: false })
        .limit(5);
      if (error) throw error;
      return data as Lead[];
    },
    staleTime: 60000,
  });
}

export function useLead(id: string | null) {
  return useQuery({
    queryKey: ['lead', id],
    queryFn: async () => {
      if (!id) return null;
      const { data, error } = await supabase
        .from('leads')
        .select('*')
        .eq('id', id)
        .single();
      if (error) throw error;
      return data as Lead;
    },
    enabled: !!id,
    staleTime: 60000,
  });
}

export function useCreateLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (lead: Partial<Lead>) => {
      const { data, error } = await supabase
        .from('leads')
        .insert(lead)
        .select()
        .single();
      if (error) throw error;
      return data as Lead;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['leads'] });
      toast.success('Lead created');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, updates }: { id: string; updates: Partial<Lead> }) => {
      const { data, error } = await supabase
        .from('leads')
        .update(updates)
        .eq('id', id)
        .select()
        .single();
      if (error) throw error;
      return data as Lead;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['leads'] });
      toast.success('Lead updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteLead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await supabase.from('leads').delete().eq('id', id);
      if (error) throw error;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['leads'] });
      toast.success('Lead deleted');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useOutreachActivity(leadId: string | null) {
  return useQuery({
    queryKey: ['outreach', leadId],
    queryFn: async () => {
      if (!leadId) return [];
      const { data, error } = await supabase
        .from('outreach_activity')
        .select('*')
        .eq('lead_id', leadId)
        .order('created_at', { ascending: false });
      if (error) throw error;
      return data;
    },
    enabled: !!leadId,
    staleTime: 30000,
  });
}

export function useLogActivity() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (activity: {
      lead_id: string;
      channel: string;
      direction: string;
      status?: string;
      message?: string;
      response?: string;
    }) => {
      const { error } = await supabase.from('outreach_activity').insert(activity);
      if (error) throw error;
      // Increment contact attempts
      await supabase.rpc('increment_contact_attempts', { lead_id: activity.lead_id });
    },
    onSuccess: (_, v) => {
      qc.invalidateQueries({ queryKey: ['outreach', v.lead_id] });
      qc.invalidateQueries({ queryKey: ['leads'] });
      toast.success('Activity logged');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
