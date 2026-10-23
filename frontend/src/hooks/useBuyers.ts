import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import type { Buyer, LandBuyerType } from '@/types';
import { toast } from 'sonner';
import { buyerChangeMessage, saveBuyerChange } from '@/lib/buyerChanges';
import { queryAllConfirmed } from '@/lib/queryAll';
import { useEffect, useState } from 'react';
import { createManualBuyer, pendingManualBuyer, recoverManualBuyer, type PendingBuyer, type ManualBuyerReceipt } from '@/lib/manualBuyer';

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
  const [pending, setPending] = useState<PendingBuyer | null>(null);
  const [ready, setReady] = useState(false);
  const [checking, setChecking] = useState(false);
  const [recoveryError, setRecoveryError] = useState('');
  useEffect(() => {
    let active = true;
    void pendingManualBuyer().then(value => { if (active) { setPending(value); setReady(true); } })
      .catch(() => { if (active) setRecoveryError('Saved buyer recovery is unavailable. Sign in again or review the existing request before another save.'); });
    return () => { active = false; };
  }, []);
  const accepted = (receipt: ManualBuyerReceipt | null) => {
    if (!receipt || receipt.state === 'pending') return toast.info('No saved result is confirmed yet. Retry the original save or stop the request.');
    void qc.invalidateQueries({ queryKey: ['buyers'] });
    if (receipt.state === 'canceled') toast.success('Pending buyer request stopped');
    else toast.success(receipt.current_exists ? 'Buyer save confirmed. SMS and email consent remain separate.' : 'Creation recorded; this buyer has since been deleted. It was not recreated.');
  };
  const mutation = useMutation({
    mutationFn: (buyer: BuyerWrite) => createManualBuyer(buyer, setPending),
    onSuccess: receipt => {
      accepted(receipt);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const recover = async (cancel: boolean) => {
    setChecking(true);
    try { const receipt = await recoverManualBuyer(cancel, setPending); accepted(receipt); return receipt; }
    catch (error) { toast.error(error instanceof Error ? error.message : 'Buyer receipt is unconfirmed'); throw error; }
    finally { setChecking(false); }
  };
  return { ...mutation, pending, ready, checking, recoveryError,
    checkPending: () => recover(false), cancelPending: () => recover(true) };
}

export function useUpdateBuyer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, updates, expected }: { id: string; updates: BuyerWrite; expected: Buyer }) => {
      if (expected.id !== id) throw new Error('Original buyer record is required');
      const result = await saveBuyerChange('update', expected as unknown as Record<string, unknown>, updates as Record<string, unknown>);
      if (result.state !== 'updated') throw new Error(buyerChangeMessage(result.state));
      return result.buyer as unknown as Buyer;
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['buyers'] }); toast.success('Buyer edit recorded. Refresh for current details.'); },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteBuyer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (buyer: Buyer) => {
      const result = await saveBuyerChange('delete', buyer as unknown as Record<string, unknown>, null);
      if (result.state !== 'deleted') throw new Error(buyerChangeMessage(result.state));
      return result;
    },
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['buyers'] }); toast.success('Buyer deletion recorded'); },
    onError: (e: Error) => toast.error(e.message),
  });
}
