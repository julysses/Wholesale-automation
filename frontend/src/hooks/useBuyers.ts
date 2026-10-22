import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import type { Buyer, LandBuyerType } from '@/types';
import { toast } from 'sonner';
import { queryAllConfirmed } from '@/lib/queryAll';

interface BuyersFilter {
  search?: string;
  tier?: string;
  active?: boolean;
}

export type BuyerWrite = Omit<Partial<Buyer>, 'min_price' | 'max_price' | 'close_speed_days' | 'pof_amount' | 'land_buyer_type' | 'active' | 'buys_land' | 'buys_infill'> & {
  active?: boolean | null;
  buys_land?: boolean | null;
  buys_infill?: boolean | null;
  land_buyer_type?: LandBuyerType | null;
  min_price?: number | null;
  max_price?: number | null;
  close_speed_days?: number | null;
  pof_amount?: number | null;
};

export function useBuyers(filters: BuyersFilter = {}) {
  const { search, tier, active } = filters;

  return useQuery({
    queryKey: ['buyers', 'all-pages'],
    queryFn: () => queryAllConfirmed<Buyer>((from, to) => supabase.from('buyers')
      .select('*', { count: 'exact' }).order('created_at', { ascending: false })
      .order('id', { ascending: true }).range(from, to), 'Buyers'),
    select: rows => rows.filter(buyer => (!tier || buyer.tier === tier)
      && (active === undefined || buyer.active === active)
      && (!search || [buyer.first_name, buyer.last_name, buyer.company, buyer.email, buyer.phone]
        .some(value => String(value || '').toLowerCase().includes(search.toLowerCase())))),
    staleTime: 60000,
  });
}

export function useCreateBuyer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (buyer: BuyerWrite) => {
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
    mutationFn: async ({ id, updates }: { id: string; updates: BuyerWrite }) => {
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
