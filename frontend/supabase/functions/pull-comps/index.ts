/**
 * Supabase Edge Function: pull-comps
 *
 * Pulls comparable sales from Zillow + Redfin via RealtyAPI,
 * scores each comp by similarity to subject property,
 * stores top 15 in the comps table, then fires compute-arv.
 *
 * Similarity scoring (0–100 pts):
 *   Sqft delta   35 pts — linear decay 0% → >20%
 *   Proximity    30 pts — linear decay 0.0mi → 0.5mi
 *   Recency      20 pts — linear decay 0 → 180 days
 *   Bed match    10 pts — exact=10, ±1=5, ±2+=0
 *   Bath match    5 pts — exact=5, ±0.5=3, ±1+=0
 *
 * Comps scoring <40 excluded before passing to Claude.
 * Auto-expands to 1.0mi / 180 days if <5 qualified comps found.
 *
 * Secrets: REALTY_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY
 */

import { serve } from 'https://deno.land/std@0.168.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

// ── Similarity scoring ────────────────────────────────────────────────────────
function scoreComp(
  comp: { sqft?: number; distance_miles?: number; sale_date?: string; bedrooms?: number; bathrooms?: number },
  subject: { sqft: number; beds: number; baths: number }
): number {
  // Sqft score (35 pts)
  const sqftDelta = subject.sqft > 0
    ? Math.abs((comp.sqft ?? 0) - subject.sqft) / subject.sqft
    : 1;
  const sqftScore = Math.max(0, 35 * (1 - sqftDelta / 0.20));

  // Proximity score (30 pts)
  const dist = comp.distance_miles ?? 0;
  const distScore = Math.max(0, 30 * (1 - dist / 0.5));

  // Recency score (20 pts)
  const daysSince = comp.sale_date
    ? (Date.now() - new Date(comp.sale_date).getTime()) / 86_400_000
    : 180;
  const recencyScore = Math.max(0, 20 * (1 - daysSince / 180));

  // Bed match (10 pts)
  const bedDiff = Math.abs((comp.bedrooms ?? 0) - (subject.beds ?? 0));
  const bedScore = bedDiff === 0 ? 10 : bedDiff === 1 ? 5 : 0;

  // Bath match (5 pts)
  const bathDiff = Math.abs((comp.bathrooms ?? 0) - (subject.baths ?? 0));
  const bathScore = bathDiff === 0 ? 5 : bathDiff <= 0.5 ? 3 : 0;

  return sqftScore + distScore + recencyScore + bedScore + bathScore;
}

function deduplicateByAddress(comps: any[]): any[] {
  const seen = new Set<string>();
  return comps.filter((c) => {
    const key = ((c.address as string) ?? '').toLowerCase().replace(/\s+/g, '');
    if (!key || seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

async function fetchComps(
  zpid: string,
  address: string,
  radius: number,
  days: number,
  realtyHeaders: Record<string, string>
): Promise<{ zillow: any[]; redfin: any[] }> {
  const [zillowRes, redfinRes] = await Promise.all([
    fetch(
      `https://api.realtyapi.io/v1/zillow/comps?zpid=${zpid}&days=${days}&radius=${radius}`,
      { headers: realtyHeaders }
    ).then((r) => r.json()),
    fetch(
      `https://api.realtyapi.io/v1/redfin/sold?address=${encodeURIComponent(address)}&radius=${radius}&days=${days}`,
      { headers: realtyHeaders }
    ).then((r) => r.json()),
  ]);
  return {
    zillow: zillowRes.comps ?? [],
    redfin: redfinRes.results ?? [],
  };
}

// ── Main handler ──────────────────────────────────────────────────────────────
serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { lead_id, zpid, sqft, beds, baths, address, zip } = await req.json();
    if (!lead_id || !zpid || !address) {
      return new Response(JSON.stringify({ error: 'lead_id, zpid, and address required' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const REALTY_API_KEY = Deno.env.get('REALTY_API_KEY')!;
    const SUPABASE_URL   = Deno.env.get('SUPABASE_URL')!;
    const SERVICE_KEY    = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const ANON_KEY       = Deno.env.get('SUPABASE_ANON_KEY')!;

    const supabase      = createClient(SUPABASE_URL, SERVICE_KEY);
    const realtyHeaders = { 'X-API-Key': REALTY_API_KEY };
    const subjectSqft   = Number(sqft) || 0;
    const subjectBeds   = Number(beds) || 0;
    const subjectBaths  = Number(baths) || 0;

    // ── Pull initial comps (0.5mi, 90 days) ──────────────────────────────────
    const { zillow, redfin } = await fetchComps(zpid, address, 0.5, 90, realtyHeaders);

    let allComps = deduplicateByAddress([
      ...zillow.map((c: any) => ({ ...c, source: 'zillow' })),
      ...redfin.map((c: any) => ({ ...c, source: 'redfin' })),
    ]);

    // Hard sqft filter ±20%
    const sqftMin = subjectSqft * 0.80;
    const sqftMax = subjectSqft * 1.20;
    let filtered = subjectSqft > 0
      ? allComps.filter((c) => (c.sqft ?? 0) >= sqftMin && (c.sqft ?? 0) <= sqftMax)
      : allComps;

    // Score each comp
    let scored = filtered
      .map((c) => ({
        ...c,
        similarity_score: Math.round(scoreComp(c, { sqft: subjectSqft, beds: subjectBeds, baths: subjectBaths }) * 100) / 100,
        price_per_sqft:   c.sqft > 0 ? Math.round((c.sale_price / c.sqft) * 100) / 100 : null,
      }))
      .sort((a, b) => b.similarity_score - a.similarity_score);

    // Auto-expand if <5 qualified comps
    const qualifiedCount = scored.filter((c) => c.similarity_score >= 40).length;
    if (qualifiedCount < 5) {
      const expanded = await fetchComps(zpid, address, 1.0, 180, realtyHeaders);
      const expandedComps = deduplicateByAddress([
        ...expanded.zillow.map((c: any) => ({ ...c, source: 'zillow_expanded' })),
        ...expanded.redfin.map((c: any) => ({ ...c, source: 'redfin_expanded' })),
      ]);

      const expandedFiltered = subjectSqft > 0
        ? expandedComps.filter((c) => (c.sqft ?? 0) >= sqftMin && (c.sqft ?? 0) <= sqftMax)
        : expandedComps;

      const expandedScored = expandedFiltered.map((c) => ({
        ...c,
        similarity_score: Math.round(scoreComp(c, { sqft: subjectSqft, beds: subjectBeds, baths: subjectBaths }) * 100) / 100,
        price_per_sqft:   c.sqft > 0 ? Math.round((c.sale_price / c.sqft) * 100) / 100 : null,
      }));

      // Merge, re-deduplicate, re-sort
      scored = deduplicateByAddress([...scored, ...expandedScored])
        .sort((a, b) => b.similarity_score - a.similarity_score);
    }

    // ── Store top 15 in comps table ───────────────────────────────────────────
    const top15 = scored.slice(0, 15);
    if (top15.length > 0) {
      // Delete existing comps for this lead before inserting fresh set
      await supabase.from('comps').delete().eq('lead_id', lead_id);

      await supabase.from('comps').insert(
        top15.map((c) => ({
          lead_id,
          address:          c.address ?? '',
          city:             c.city ?? null,
          zip_code:         c.zipCode ?? c.zip ?? null,
          sale_price:       c.sale_price ?? null,
          sale_date:        c.sale_date ?? null,
          sqft:             c.sqft ?? null,
          bedrooms:         c.bedrooms ?? null,
          bathrooms:        c.bathrooms ?? null,
          price_per_sqft:   c.price_per_sqft ?? null,
          distance_miles:   c.distance_miles ?? null,
          source:           c.source,
          similarity_score: c.similarity_score,
          raw_payload:      c,
          fetched_at:       new Date().toISOString(),
        }))
      );
    }

    // ── Fire compute-arv with top 8 qualified comps ───────────────────────────
    const qualifiedComps = scored.filter((c) => c.similarity_score >= 40).slice(0, 8);

    fetch(`${SUPABASE_URL}/functions/v1/compute-arv`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${ANON_KEY}`,
      },
      body: JSON.stringify({
        lead_id,
        subject: { address, sqft: subjectSqft, beds: subjectBeds, baths: subjectBaths, zip },
        comps: qualifiedComps,
      }),
    }).catch(() => { /* fire-and-forget */ });

    return new Response(
      JSON.stringify({ comp_count: scored.length, qualified: qualifiedComps.length }),
      { status: 200, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  } catch (err) {
    return new Response(
      JSON.stringify({ error: err instanceof Error ? err.message : 'Unknown error' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
