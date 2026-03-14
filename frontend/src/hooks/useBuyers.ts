import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import type { Buyer } from '@/types';
import { toast } from 'sonner';

interface BuyersFilter {
  search?: string;
  tier?: string;
  active?: boolean;
}

export function useBuyers(filters: BuyersFilter = {}) {
  const { search, tier, active } = filters;

  return useQuery({
    queryKey: ['buyers', filters],
    queryFn: async () => {
      let query = supabase
        .from('buyers')
        .select('*')
        .order('created_at', { ascending: false });

      if (tier) query = query.eq('tier', tier);
      if (active !== undefined) query = query.eq('active', active);
      if (search) {
        query = query.or(
          `first_name.ilike.%${search}%,last_name.ilike.%${search}%,company.ilike.%${search}%,email.ilike.%${search}%,phone.ilike.%${search}%`
        );
      }

      const { data, error } = await query;
      if (error) throw error;
      return data as Buyer[];
    },
    staleTime: 60000,
  });
}

export function useCreateBuyer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (buyer: Partial<Buyer>) => {
      const { data, error } = await supabase
        .from('buyers')
        .insert(buyer)
        .select()
        .single();
      if (error) throw error;
      return data as Buyer;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['buyers'] });
      toast.success('Buyer added');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useUpdateBuyer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, updates }: { id: string; updates: Partial<Buyer> }) => {
      const { data, error } = await supabase
        .from('buyers')
        .update(updates)
        .eq('id', id)
        .select()
        .single();
      if (error) throw error;
      return data as Buyer;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['buyers'] });
      toast.success('Buyer updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteBuyer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => {
      const { error } = await supabase.from('buyers').delete().eq('id', id);
      if (error) throw error;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['buyers'] });
      toast.success('Buyer deleted');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
