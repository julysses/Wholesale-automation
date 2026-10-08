import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useState } from 'react';
import { supabase } from '@/lib/supabase';
import type { Deal } from '@/types';
import { useDealStore } from '@/stores/useDealStore';
import { toast } from 'sonner';
import { localDateString } from '@/lib/taskDates';
import { queryAll } from '@/lib/queryAll';
import { createPipelineDeal, updatePipelineDeal, pendingDeal, type PendingDeal } from '@/lib/dealWrites';

export type DealWrite = Omit<Partial<Deal>, 'contract_date' | 'inspection_deadline' | 'closing_date' | 'actual_close_date' | 'buyer_id' | 'assigned_to' | 'earnest_money'> & {
  earnest_money?: number | null;
  contract_date?: string | null;
  inspection_deadline?: string | null;
  buyer_id?: string | null;
  assigned_to?: string | null;
  closing_date?: string | null;
  actual_close_date?: string | null;
};

export function useDeals() {
  const id = useId();
  const setDeals = useDealStore((s) => s.setDeals);
  const qc = useQueryClient();

  const query = useQuery({
    queryKey: ['deals'],
    queryFn: async () => {
      const deals = await queryAll<Deal>((from, to) => supabase
        .from('deals')
        .select('*, lead:leads(property_address, city, state, zip_code, property_type, bedrooms, bathrooms), buyer:buyers(first_name, last_name)')
        .order('created_at', { ascending: false })
        .order('id', { ascending: false })
        .range(from, to));
      setDeals(deals);
      return deals;
    },
    staleTime: 60000,
  });

  useEffect(() => {
    const channel = supabase
      .channel(`deals-realtime-${id}`)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'deals' }, () => {
        qc.invalidateQueries({ queryKey: ['deals'] });
      })
      .subscribe();
    return () => { supabase.removeChannel(channel); };
  }, [qc, id]);

  return query;
}

export function useUpcomingClosings() {
  const in14Days = new Date();
  in14Days.setDate(in14Days.getDate() + 14);
  const today = localDateString();

  return useQuery({
    queryKey: ['deals', 'upcoming-closings', today],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('deals')
        .select('*, lead:leads(property_address, city)')
        .gte('closing_date', today)
        .lte('closing_date', localDateString(in14Days))
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
  const [pendingCreate, setPendingCreate] = useState<PendingDeal | null>(() => {
    try { return pendingDeal(); } catch { return null; }
  });
  const mutation = useMutation({
    mutationFn: (deal: DealWrite) => createPipelineDeal(deal, setPendingCreate),
    onSuccess: async () => {
      await Promise.all(['deals','kpi','reports','tasks'].map(key => qc.invalidateQueries({ queryKey:[key] }))).catch(() => {});
      toast.success('Deal created');
    },
    onError: (error: Error) => toast.error(error.message),
  });
  return { ...mutation, pendingCreate };
}

export function useUpdateDeal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, updates, expected_updated_at }: { id: string; updates: DealWrite; expected_updated_at: string }) =>
      updatePipelineDeal(id, expected_updated_at, updates),
    onSuccess: async saved => {
      const store = useDealStore.getState();
      store.setDeals(store.deals.map(deal => deal.id === saved.id ? { ...deal, ...saved } : deal));
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['deals'] }),
        qc.invalidateQueries({ queryKey: ['kpi'] }),
        qc.invalidateQueries({ queryKey: ['reports'] }),
        qc.invalidateQueries({ queryKey: ['tasks'] }),
      ]).catch(() => {});
      toast.success('Deal updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
