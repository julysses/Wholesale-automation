import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { supabase } from '@/lib/supabase';
import type { Deal } from '@/types';
import { useDealStore } from '@/stores/useDealStore';
import { toast } from 'sonner';

export function useDeals() {
  const setDeals = useDealStore((s) => s.setDeals);
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: ['deals'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('deals')
        .select('*, lead:leads(property_address, city, state, zip_code), buyer:buyers(first_name, last_name)')
        .order('created_at', { ascending: false });
      if (error) throw error;
      const deals = data as Deal[];
      setDeals(deals);
      return deals;
    },
    staleTime: 60000,
  });

  useEffect(() => {
    const channel = supabase
      .channel('deals-realtime')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'deals' }, () => {
        qc.invalidateQueries({ queryKey: ['deals'] });
      })
      .subscribe();
    return () => { supabase.removeChannel(channel); };
  }, [qc]);

  return query;
}

export function useUpcomingClosings() {
  const in14Days = new Date(Date.now() + 14 * 86400000).toISOString();
  const today = new Date().toISOString();

  return useQuery({
    queryKey: ['deals', 'upcoming-closings'],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('deals')
        .select('*, lead:leads(property_address, city)')
        .gte('closing_date', today.split('T')[0])
        .lte('closing_date', in14Days.split('T')[0])
        .not('stage', 'in', '("closed","cancelled")')
        .order('closing_date', { ascending: true });
      if (error) throw error;
      return data as Deal[];
    },
    staleTime: 60000,
  });
}

export function useCreateDeal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (deal: Partial<Deal>) => {
      const { data, error } = await supabase
        .from('deals')
        .insert(deal)
        .select()
        .single();
      if (error) throw error;
      return data as Deal;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['deals'] });
      toast.success('Deal created');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateDeal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, updates }: { id: string; updates: Partial<Deal> }) => {
      const { data, error } = await supabase
        .from('deals')
        .update(updates)
        .eq('id', id)
        .select()
        .single();
      if (error) throw error;
      return data as Deal;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['deals'] });
      toast.success('Deal updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
