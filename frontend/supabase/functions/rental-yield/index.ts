/**
 * Supabase Edge Function: rental-yield
 *
 * Pulls LTR (Apartments.com) + STR (Airbnb) market data via RealtyAPI
 * for a given zip and bed count, computes gross yields, flags BTR-eligible
 * deals, and upserts into rental_yield table.
 *
 * BTR flag thresholds:
 *   gross_yield_ltr >= 7.0%  AND  ltr_monthly >= $1,800
 *
 * Secrets: REALTY_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
 */

import { serve } from 'https://deno.land/std@0.168.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { lead_id, zip, beds, arv_mid } = await req.json();
    if (!lead_id || !zip) {
      return new Response(JSON.stringify({ error: 'lead_id and zip required' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const REALTY_API_KEY = Deno.env.get('REALTY_API_KEY')!;
    const SUPABASE_URL   = Deno.env.get('SUPABASE_URL')!;
    const SERVICE_KEY    = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;

    const supabase      = createClient(SUPABASE_URL, SERVICE_KEY);
    const realtyHeaders = { 'X-API-Key': REALTY_API_KEY };
    const bedCount      = Number(beds) || 3;
    const arvMid        = Number(arv_mid) || 0;

    // ── Pull LTR + STR data in parallel ──────────────────────────────────────
    const [ltrRes, strRes] = await Promise.all([
      fetch(
        `https://api.realtyapi.io/v1/apartments/rent-estimate?zip=${zip}&beds=${bedCount}`,
        { headers: realtyHeaders }
      ).then((r) => r.json()),
      fetch(
        `https://api.realtyapi.io/v1/airbnb/market?zip=${zip}&beds=${bedCount}`,
        { headers: realtyHeaders }
      ).then((r) => r.json()),
    ]);

    const ltr_monthly   = ltrRes.median_rent ?? ltrRes.estimated_rent ?? null;
    const str_adr       = strRes.avg_daily_rate ?? strRes.adr ?? null;
    const str_occupancy = strRes.avg_occupancy_rate ?? strRes.occupancy_rate ?? null;

    const str_monthly = (str_adr != null && str_occupancy != null)
      ? Math.round(str_adr * 30 * str_occupancy)
      : null;

    // Gross yield = (annual rent / ARV) × 100
    const gross_yield_ltr = (arvMid > 0 && ltr_monthly != null)
      ? parseFloat(((ltr_monthly * 12 / arvMid) * 100).toFixed(2))
      : null;
    const gross_yield_str = (arvMid > 0 && str_monthly != null)
      ? parseFloat(((str_monthly * 12 / arvMid) * 100).toFixed(2))
      : null;

    // BTR flag
    const btr_eligible = (
      gross_yield_ltr != null && gross_yield_ltr >= 7.0 &&
      ltr_monthly != null && ltr_monthly >= 1800
    );

    // ── Upsert rental_yield (one row per lead, replace on re-run) ────────────
    await supabase.from('rental_yield').upsert(
      {
        lead_id,
        ltr_monthly_est: ltr_monthly,
        str_monthly_est: str_monthly,
        str_occupancy,
        str_adr,
        gross_yield_ltr,
        gross_yield_str,
        fetched_at: new Date().toISOString(),
      },
      { onConflict: 'lead_id' }
    );

    // ── Tag BTR-eligible leads ────────────────────────────────────────────────
    if (btr_eligible) {
      // Fetch current tags, append 'btr-eligible' if not already present
      const { data: lead } = await supabase
        .from('leads')
        .select('tags')
        .eq('id', lead_id)
        .single();

      const currentTags: string[] = lead?.tags ?? [];
      if (!currentTags.includes('btr-eligible')) {
        await supabase
          .from('leads')
          .update({ tags: [...currentTags, 'btr-eligible'] })
          .eq('id', lead_id);
      }
    }

    return new Response(
      JSON.stringify({ ltr_monthly, str_monthly, gross_yield_ltr, gross_yield_str, btr_eligible }),
      { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  } catch (err) {
    return new Response(
      JSON.stringify({ error: err instanceof Error ? err.message : 'Unknown error' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
