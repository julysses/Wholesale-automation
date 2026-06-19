/**
 * Supabase Edge Function: market-pulse
 *
 * Weekly cron job (Sunday 7AM CST / 13:00 UTC) that fetches Redfin market
 * data for each DFW target zip, scores market temperature, stores in
 * market_pulse table, then calls Claude for an acquisition focus recommendation
 * stored as an app_notifications record.
 *
 * Market temperature scoring (2+ metrics in same column wins):
 *   Metric           Hot        Warm       Cool
 *   Avg DOM          <15 days   15–30      >45
 *   List/Sale ratio  >1.02      1.00–1.02  <0.97
 *   Price cut %      <10%       10–20%     >30%
 *
 * Ties → neutral
 *
 * Secrets: REALTY_API_KEY, ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
 */

import { serve } from 'https://deno.land/std@0.168.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const DEFAULT_TARGET_ZIPS = [
  '75050', '75051', '75052',
  '75061', '75062',
  '75104', '75114',
  '76021', '76022',
  '75019',
  '75208', '75211',
  '76010', '76011',
  '75115', '75116',
];

function computeMarketTemp(market: {
  avg_days_on_market?: number;
  list_to_sale_ratio?: number;
  pct_listings_with_price_cut?: number;
}): 'hot' | 'warm' | 'neutral' | 'cool' {
  let hot = 0, warm = 0, cool = 0;

  const dom = market.avg_days_on_market;
  if (dom != null) {
    if (dom < 15)      hot++;
    else if (dom <= 30) warm++;
    else if (dom > 45)  cool++;
  }

  const lts = market.list_to_sale_ratio;
  if (lts != null) {
    if (lts > 1.02)        hot++;
    else if (lts >= 1.00)  warm++;
    else if (lts < 0.97)   cool++;
  }

  const pct = market.pct_listings_with_price_cut;
  if (pct != null) {
    if (pct < 10)       hot++;
    else if (pct <= 20)  warm++;
    else if (pct > 30)   cool++;
  }

  if (hot >= 2)  return 'hot';
  if (cool >= 2) return 'cool';
  if (warm >= 2) return 'warm';
  return 'neutral';
}

async function getAcquisitionFocus(
  pulseRows: any[],
  anthropicKey: string
): Promise<string> {
  const prompt = `You are a real estate acquisitions advisor for a DFW wholesaler.
Here is this week's market pulse data by zip code:
${JSON.stringify(pulseRows, null, 2)}

Based on market temperature, DOM trends, and price cut percentages:
1. Identify the top 3 zip codes to focus acquisition efforts on this week
2. Explain the opportunity in each zip in one sentence
3. Flag any zips that are deteriorating and should be de-prioritized

Respond in plain text, no JSON. Keep it to 150 words max. Be direct and specific.`;

  const res = await fetch('https://api.anthropic.com/v1/messages', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': anthropicKey,
      'anthropic-version': '2023-06-01',
    },
    body: JSON.stringify({
      model: 'claude-sonnet-4-6',
      max_tokens: 300,
      messages: [{ role: 'user', content: prompt }],
    }),
  });

  if (!res.ok) return 'Market advisory unavailable this week.';

  const data = await res.json();
  return data.content?.[0]?.text ?? 'Market advisory unavailable this week.';
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const REALTY_API_KEY  = Deno.env.get('REALTY_API_KEY')!;
    const ANTHROPIC_KEY   = Deno.env.get('ANTHROPIC_API_KEY')!;
    const SUPABASE_URL    = Deno.env.get('SUPABASE_URL')!;
    const SERVICE_KEY     = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;

    const supabase      = createClient(SUPABASE_URL, SERVICE_KEY);
    const realtyHeaders = { 'X-API-Key': REALTY_API_KEY };

    // Load target zips (defaults + app_config override)
    let targetZips = [...DEFAULT_TARGET_ZIPS];
    try {
      const { data: cfg } = await supabase
        .from('app_config')
        .select('value')
        .eq('key', 'TARGET_ZIPS')
        .single();
      if (cfg?.value) {
        const extraZips = (cfg.value as string).split(',').map((z: string) => z.trim()).filter(Boolean);
        targetZips = [...new Set([...targetZips, ...extraZips])];
      }
    } catch { /* use defaults */ }

    const insertedRows: any[] = [];

    // ── Fetch + store market data per zip ─────────────────────────────────────
    for (const zip of targetZips) {
      try {
        const marketRes = await fetch(
          `https://api.realtyapi.io/v1/redfin/market?zip=${zip}`,
          { headers: realtyHeaders }
        );
        const market = await marketRes.json();
        const temp   = computeMarketTemp(market);

        const row = {
          zip_code:           zip,
          median_list_price:  market.median_list_price ?? null,
          median_ppsf:        market.median_price_per_sqft ?? null,
          avg_dom:            market.avg_days_on_market ?? null,
          list_to_sale_ratio: market.list_to_sale_ratio ?? null,
          price_cut_pct:      market.pct_listings_with_price_cut ?? null,
          market_temp:        temp,
          fetched_at:         new Date().toISOString(),
        };

        await supabase.from('market_pulse').insert(row);
        insertedRows.push(row);
      } catch (zipErr) {
        console.error(`market-pulse: error for zip ${zip}:`, zipErr);
      }
    }

    // ── Claude acquisition focus recommendation ──────────────────────────────
    if (insertedRows.length > 0 && ANTHROPIC_KEY) {
      const focusRec = await getAcquisitionFocus(insertedRows, ANTHROPIC_KEY);

      await supabase.from('app_notifications').insert({
        type:       'weekly_market_focus',
        content:    focusRec,
        created_at: new Date().toISOString(),
      });
    }

    return new Response(
      JSON.stringify({ zips_processed: insertedRows.length }),
      { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  } catch (err) {
    return new Response(
      JSON.stringify({ error: err instanceof Error ? err.message : 'Unknown error' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
