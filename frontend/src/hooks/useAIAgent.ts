import { apiFetch } from '@/lib/api';
/**
 * AI Agent hooks — calls our FastAPI Python backend (/api/ai/*) instead of
 * Supabase Edge Functions.  The Python agents use Claude claude-sonnet-4-6 and
 * enforce Sections 4 & 5 compliance rules automatically.
 */

import { useState } from 'react';
import { useUpdateLead } from './useLeads';
import type {
  QualificationResult,
  OfferResult,
  OutreachVariation,
  BuyerMatchResult,
} from '@/types';

const API_BASE = '/api/ai';

async function callAgent<T>(endpoint: string, body: unknown): Promise<T> {
  const res = await apiFetch(`${API_BASE}/${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? `Agent error ${res.status}`);
  }
  return res.json();
}

// ── Lead Qualifier ────────────────────────────────────────────────────────────

export function useLeadQualifier() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QualificationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const updateLead = useUpdateLead();

  const qualify = async (params: {
    lead_id: string;
    property_address: string;
    city?: string;
    state?: string;
    owner_first_name?: string;
    owner_last_name?: string;
    motivation_tag?: string;
    seller_notes?: string;
    estimated_equity_pct?: number;
    loan_balance?: number;
    estimated_arv?: number;
    contact_attempts?: number;
  }) => {
    setLoading(true);
    setError(null);
    try {
      const data = await callAgent<QualificationResult>('qualify-lead', params);
      setResult(data);

      // Write scores back to Supabase via the lead mutation hook
      await updateLead.mutateAsync({
        id: params.lead_id,
        updates: {
          score_motivation: data.score_motivation,
          score_timeline: data.score_timeline,
          score_equity: data.score_equity,
          score_condition: data.score_condition,
          score_flexibility: data.score_flexibility,
          ai_qualification_summary: data.qualification_summary,
          status:
            data.tier === 'HOT'
              ? 'qualified_hot'
              : data.tier === 'WARM'
              ? 'qualified_warm'
              : 'qualified_cold',
        },
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to qualify lead');
    } finally {
      setLoading(false);
    }
  };

  return { qualify, loading, result, error };
}

// ── Offer Generator ───────────────────────────────────────────────────────────

export function useOfferGenerator() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<OfferResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const generate = async (params: {
    lead_id?: string;
    property_address: string;
    city?: string;
    motivation_tag?: string;
    ai_qualification_summary?: string;
    asking_price?: number;
    mao?: number;
    arv?: number;
    repair_estimate?: number;
  }) => {
    setLoading(true);
    setError(null);
    try {
      const data = await callAgent<OfferResult>('generate-offer', params);
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate offer');
    } finally {
      setLoading(false);
    }
  };

  return { generate, loading, result, error };
}

// ── Outreach Writer ───────────────────────────────────────────────────────────

export function useOutreachWriter() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<OutreachVariation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const write = async (params: {
    lead_id?: string;
    property_address: string;
    city?: string;
    owner_first_name?: string;
    motivation_tag?: string;
    contact_attempts?: number;
    channel: string;
    tone: string;
  }) => {
    setLoading(true);
    setError(null);
    try {
      const data = await callAgent<OutreachVariation[]>('write-outreach', params);
      setResult(Array.isArray(data) ? data : [data]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to write outreach');
    } finally {
      setLoading(false);
    }
  };

  return { write, loading, result, error };
}

// ── Buyer Matcher ─────────────────────────────────────────────────────────────

export function useBuyerMatcher() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BuyerMatchResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const match = async (params: {
    deal_id?: string;
    property_address: string;
    contract_price?: number;
    buyer_price?: number;
    arv?: number;
    repair_estimate?: number;
    property_type?: string;
    bedrooms?: number;
    bathrooms?: number;
    zip_code?: string;
    closing_date?: string;
  }) => {
    setLoading(true);
    setError(null);
    try {
      const data = await callAgent<BuyerMatchResult>('match-buyers', params);
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to match buyers');
    } finally {
      setLoading(false);
    }
  };

  return { match, loading, result, error };
}
