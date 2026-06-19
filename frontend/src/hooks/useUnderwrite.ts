import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { supabase } from '@/lib/supabase';
import type { PropertyEnrichment, ArvResult, Comp, RentalYield } from '@/types';
import { toast } from 'sonner';

// ── Property Enrichment ───────────────────────────────────────────────────────

export function usePropertyEnrichment(leadId: string) {
  return useQuery<PropertyEnrichment | null>({
    queryKey: ['property_enrichment', leadId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('property_enrichment')
        .select('*')
        .eq('lead_id', leadId)
        .maybeSingle();
      if (error) throw error;
      return data as PropertyEnrichment | null;
    },
    staleTime: 5 * 60 * 1000,
    enabled: !!leadId,
  });
}

// ── ARV Result ────────────────────────────────────────────────────────────────

export function useArvResult(leadId: string) {
  return useQuery<ArvResult | null>({
    queryKey: ['arv_results', leadId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('arv_results')
        .select('*')
        .eq('lead_id', leadId)
        .order('computed_at', { ascending: false })
        .limit(1)
        .maybeSingle();
      if (error) throw error;
      return data as ArvResult | null;
    },
    staleTime: 5 * 60 * 1000,
    enabled: !!leadId,
  });
}

// ── Comps ─────────────────────────────────────────────────────────────────────

export function useLeadComps(leadId: string) {
  return useQuery<Comp[]>({
    queryKey: ['comps', leadId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('comps')
        .select('*')
        .eq('lead_id', leadId)
        .order('similarity_score', { ascending: false });
      if (error) throw error;
      return (data ?? []) as Comp[];
    },
    staleTime: 5 * 60 * 1000,
    enabled: !!leadId,
  });
}

// ── Rental Yield ──────────────────────────────────────────────────────────────

export function useRentalYield(leadId: string) {
  return useQuery<RentalYield | null>({
    queryKey: ['rental_yield', leadId],
    queryFn: async () => {
      const { data, error } = await supabase
        .from('rental_yield')
        .select('*')
        .eq('lead_id', leadId)
        .maybeSingle();
      if (error) throw error;
      return data as RentalYield | null;
    },
    staleTime: 5 * 60 * 1000,
    enabled: !!leadId,
  });
}

// ── Refresh Underwrite ────────────────────────────────────────────────────────
// Manually re-triggers the full enrichment chain for a lead.

export function useRefreshUnderwrite(leadId: string) {
  const qc = useQueryClient();

  return useMutation({
    mutationFn: async ({ address }: { address: string }) => {
      const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL as string;
      const ANON_KEY     = import.meta.env.VITE_SUPABASE_ANON_KEY as string;

      const res = await fetch(`${SUPABASE_URL}/functions/v1/enrich-property`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${ANON_KEY}`,
        },
        body: JSON.stringify({ lead_id: leadId, address }),
      });

      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ?? `Enrichment failed (${res.status})`);
      }

      return res.json();
    },
    onSuccess: () => {
      // Invalidate all underwrite queries for this lead after a short delay
      // to allow the async chain to complete
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ['property_enrichment', leadId] });
        qc.invalidateQueries({ queryKey: ['arv_results', leadId] });
        qc.invalidateQueries({ queryKey: ['comps', leadId] });
        qc.invalidateQueries({ queryKey: ['rental_yield', leadId] });
      }, 8000);
      toast.success('Enrichment started — data will appear in ~10 seconds');
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });
}
