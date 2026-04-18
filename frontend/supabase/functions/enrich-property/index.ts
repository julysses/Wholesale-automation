/**
 * Supabase Edge Function: enrich-property
 *
 * Triggered by DB trigger (enrich_lead_on_insert) after lead INSERT,
 * or called directly for manual refresh.
 *
 * Flow:
 *   1. Search Zillow via RealtyAPI → get zpid
 *   2. Fallback to Realtor.com if no zpid found
 *   3. Fetch full property detail
 *   4. Upsert into property_enrichment table
 *   5. Fire pull-comps asynchronously
 *
 * Secrets: REALTY_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY
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
    const { lead_id, address } = await req.json();
    if (!lead_id || !address) {
      return new Response(JSON.stringify({ error: 'lead_id and address required' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const REALTY_API_KEY = Deno.env.get('REALTY_API_KEY');
    const SUPABASE_URL   = Deno.env.get('SUPABASE_URL')!;
    const SERVICE_KEY    = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const ANON_KEY       = Deno.env.get('SUPABASE_ANON_KEY')!;

    if (!REALTY_API_KEY) {
      return new Response(JSON.stringify({ error: 'REALTY_API_KEY not configured' }), {
        status: 500,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const supabase = createClient(SUPABASE_URL, SERVICE_KEY);
    const realtyHeaders = { 'X-API-Key': REALTY_API_KEY };

    // ── Step 1: Search Zillow ────────────────────────────────────────────────
    const searchRes = await fetch(
      `https://api.realtyapi.io/v1/zillow/property/search?address=${encodeURIComponent(address)}`,
      { headers: realtyHeaders }
    );
    const searchData = await searchRes.json();
    const zpid = searchData?.results?.[0]?.zpid;

    // ── Step 2: Fallback to Realtor.com ─────────────────────────────────────
    if (!zpid) {
      const fallbackRes = await fetch(
        `https://api.realtyapi.io/v1/realtor/property/search?address=${encodeURIComponent(address)}`,
        { headers: realtyHeaders }
      );
      const fallback = await fallbackRes.json();
      const prop = fallback?.results?.[0];

      if (prop) {
        await supabase.from('property_enrichment').upsert(
          {
            lead_id,
            address,
            beds:          prop.bedrooms ?? null,
            baths:         prop.bathrooms ?? null,
            sqft:          prop.livingArea ?? null,
            year_built:    prop.yearBuilt ?? null,
            lot_size_sqft: prop.lotSize ?? null,
            property_type: prop.homeType ?? null,
            data_source:   'realtor',
            raw_payload:   prop,
          },
          { onConflict: 'lead_id' }
        );
      }

      return new Response(
        JSON.stringify({ source: 'realtor_fallback', found: !!prop }),
        { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
      );
    }

    // ── Step 3: Fetch full Zillow detail ─────────────────────────────────────
    const detailRes = await fetch(
      `https://api.realtyapi.io/v1/zillow/property/detail?zpid=${zpid}`,
      { headers: realtyHeaders }
    );
    const detail = await detailRes.json();

    // ── Step 4: Upsert into property_enrichment ───────────────────────────────
    await supabase.from('property_enrichment').upsert(
      {
        lead_id,
        address,
        beds:            detail.bedrooms ?? null,
        baths:           detail.bathrooms ?? null,
        sqft:            detail.livingArea ?? null,
        year_built:      detail.yearBuilt ?? null,
        lot_size_sqft:   detail.lotSize ?? null,
        last_sale_price: detail.lastSoldPrice ?? null,
        last_sale_date:  detail.lastSoldDate ?? null,
        zestimate:       detail.zestimate ?? null,
        tax_assessment:  detail.taxAssessedValue ?? null,
        property_type:   detail.homeType ?? null,
        zpid:            String(zpid),
        data_source:     'zillow',
        raw_payload:     detail,
      },
      { onConflict: 'lead_id' }
    );

    // ── Step 5: Fire pull-comps asynchronously ────────────────────────────────
    fetch(`${SUPABASE_URL}/functions/v1/pull-comps`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${ANON_KEY}`,
      },
      body: JSON.stringify({
        lead_id,
        zpid: String(zpid),
        sqft:    detail.livingArea,
        beds:    detail.bedrooms,
        baths:   detail.bathrooms,
        address,
        zip:     detail.zipcode ?? detail.zip,
      }),
    }).catch(() => { /* fire-and-forget */ });

    return new Response(
      JSON.stringify({ success: true, zpid }),
      { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  } catch (err) {
    return new Response(
      JSON.stringify({ error: err instanceof Error ? err.message : 'Unknown error' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
