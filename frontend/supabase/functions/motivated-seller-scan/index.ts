/**
 * Supabase Edge Function: motivated-seller-scan
 *
 * Weekly cron job (Sunday 6AM CST / 12:00 UTC) that scans active Realtor.com
 * listings across DFW target zips for motivated seller signals.
 *
 * Signal scoring model (max 100 pts):
 *   Price reduction >= 5%         30 pts
 *   Extended DOM >= 45 days        25 pts
 *   Multiple price cuts (2+)       20 pts
 *   Relisted within 60 days        15 pts
 *   Vacant flag                    10 pts
 *
 * Score >= 40 → create lead (source: motivated_seller_scan)
 * Score >= 55 → create lead + set priority = true + tags: ['motivated', 'priority']
 *
 * Target zips are hardcoded DFW markets. Can be extended via app_config table.
 *
 * Secrets: REALTY_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
 */

import { serve } from 'https://deno.land/std@0.168.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

const DEFAULT_TARGET_ZIPS = [
  '75050', '75051', '75052',  // Grand Prairie
  '75061', '75062',           // Irving
  '75104', '75114',           // Cedar Hill / Crandall
  '76021', '76022',           // Bedford
  '75019',                    // Coppell
  '75208', '75211',           // Dallas West
  '76010', '76011',           // Arlington
  '75115', '75116',           // Duncanville / Hutchins
];

function computeMotivationScore(listing: {
  price_reduced?: boolean;
  original_price?: number;
  price?: number;
  days_on_market?: number;
  price_reduction_count?: number;
  relisted?: boolean;
  vacant?: boolean;
}): number {
  let score = 0;

  // Price reduction >= 5%
  if (listing.price_reduced && listing.original_price && listing.price) {
    const cutPct = (listing.original_price - listing.price) / listing.original_price;
    if (cutPct >= 0.05) score += 30;
  }

  // Extended DOM >= 45 days
  if ((listing.days_on_market ?? 0) >= 45) score += 25;

  // Multiple price cuts
  if ((listing.price_reduction_count ?? 0) >= 2) score += 20;

  // Relisted within 60 days
  if (listing.relisted === true) score += 15;

  // Vacant flag
  if (listing.vacant === true) score += 10;

  return score;
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const REALTY_API_KEY = Deno.env.get('REALTY_API_KEY')!;
    const SUPABASE_URL   = Deno.env.get('SUPABASE_URL')!;
    const SERVICE_KEY    = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;

    const supabase      = createClient(SUPABASE_URL, SERVICE_KEY);
    const realtyHeaders = { 'X-API-Key': REALTY_API_KEY };

    // Optionally load extra zips from app_config
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
    } catch { /* app_config table may not exist; use defaults */ }

    const results = { scanned: 0, leads_created: 0, priority_leads: 0, errors: 0 };

    for (const zip of targetZips) {
      try {
        const listingsRes = await fetch(
          `https://api.realtyapi.io/v1/realtor/listings?zip=${zip}&status=for_sale&limit=50`,
          { headers: realtyHeaders }
        );
        const listingsData = await listingsRes.json();
        const listings = listingsData.results ?? [];

        for (const listing of listings) {
          results.scanned++;
          const score = computeMotivationScore(listing);

          if (score < 40) continue;

          // Check if this address already exists in leads
          const { data: existing } = await supabase
            .from('leads')
            .select('id')
            .ilike('property_address', listing.address ?? '')
            .maybeSingle();

          if (existing) continue;

          const isPriority = score >= 55;
          const tags       = isPriority ? ['motivated', 'priority'] : ['motivated'];

          await supabase.from('leads').insert({
            property_address:  listing.address ?? `Unknown-${zip}`,
            city:              listing.city ?? '',
            state:             'TX',
            zip_code:          zip,
            list_price:        listing.price ?? null,
            source:            'motivated_seller_scan',
            motivation_score:  score,
            priority:          isPriority,
            status:            'new',
            tags,
          });

          results.leads_created++;
          if (isPriority) results.priority_leads++;
        }
      } catch (zipErr) {
        results.errors++;
        console.error(`Error scanning zip ${zip}:`, zipErr);
      }
    }

    return new Response(JSON.stringify(results), {
      status: 200,
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (err) {
    return new Response(
      JSON.stringify({ error: err instanceof Error ? err.message : 'Unknown error' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
