/**
 * Supabase Edge Function: compute-arv
 *
 * Sends pre-scored comps to Claude for weighted ARV computation.
 * Stores result in arv_results, updates leads.deal_score,
 * then fires rental-yield asynchronously.
 *
 * Claude prompt instructs:
 *   - Exclude comps with similarity_score < 40
 *   - Weight remaining comps by similarity_score
 *   - ARV Mid = weighted avg PPSF × subject sqft
 *   - ARV Low = Mid × 0.90 | ARV High = Mid × 1.08
 *   - Confidence: HIGH (5+ comps >60), MEDIUM (3–4 or 40–60), LOW (<3)
 *
 * Secrets: ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY
 */

import { serve } from 'https://deno.land/std@0.168.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

function computeDealScore(confidence: string, compCount: number): number {
  let score = 0;
  if (confidence === 'high')   score += 50;
  else if (confidence === 'medium') score += 30;
  else                          score += 10;
  score += Math.min(compCount * 5, 50);
  return Math.min(score, 100);
}

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const { lead_id, subject, comps } = await req.json();
    if (!lead_id || !subject) {
      return new Response(JSON.stringify({ error: 'lead_id and subject required' }), {
        status: 400,
        headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      });
    }

    const ANTHROPIC_KEY = Deno.env.get('ANTHROPIC_API_KEY')!;
    const SUPABASE_URL  = Deno.env.get('SUPABASE_URL')!;
    const SERVICE_KEY   = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const ANON_KEY      = Deno.env.get('SUPABASE_ANON_KEY')!;

    const supabase = createClient(SUPABASE_URL, SERVICE_KEY);

    // ── Build Claude prompt ───────────────────────────────────────────────────
    const prompt = `You are a real estate underwriter computing ARV for a wholesale deal in the Dallas–Fort Worth market.

Subject property:
${JSON.stringify(subject, null, 2)}

Comparable sales (pre-scored by similarity 0–100, sorted highest first):
${JSON.stringify(comps ?? [], null, 2)}

Instructions:
1. Exclude any comp with similarity_score < 40
2. Weight each remaining comp by its similarity_score (higher score = more weight)
3. Compute weighted average price-per-sqft from the top 5 weighted comps
4. ARV Mid = weighted avg PPSF × subject sqft
5. ARV Low = ARV Mid × 0.90 (conservative)
6. ARV High = ARV Mid × 1.08 (optimistic ceiling)
7. Max Offer (70% rule) = ARV Mid × 0.70 — note this is before repair deduction
8. Confidence rating:
   - HIGH: 5+ comps with score >60
   - MEDIUM: 3–4 comps, or scores between 40–60
   - LOW: fewer than 3 comps after filter
9. Flag any outlier comps excluded and explain why

Respond ONLY with valid JSON — no markdown, no explanation outside the JSON:
{
  "arv_low": number,
  "arv_mid": number,
  "arv_high": number,
  "avg_ppsf": number,
  "comp_count_used": number,
  "confidence": "high" | "medium" | "low",
  "max_offer_before_repairs": number,
  "methodology_notes": "string"
}`;

    // ── Call Claude API ───────────────────────────────────────────────────────
    const claudeRes = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-6',
        max_tokens: 1000,
        messages: [{ role: 'user', content: prompt }],
      }),
    });

    if (!claudeRes.ok) {
      const errBody = await claudeRes.json().catch(() => ({}));
      throw new Error(errBody?.error?.message ?? `Claude API error ${claudeRes.status}`);
    }

    const claudeData = await claudeRes.json();
    const rawText = (claudeData.content[0].text as string)
      .replace(/```json|```/g, '')
      .trim();
    const arv = JSON.parse(rawText);

    // ── Store ARV result ──────────────────────────────────────────────────────
    await supabase.from('arv_results').insert({
      lead_id,
      arv_low:    arv.arv_low,
      arv_mid:    arv.arv_mid,
      arv_high:   arv.arv_high,
      avg_ppsf:   arv.avg_ppsf,
      comp_count: arv.comp_count_used,
      confidence: arv.confidence,
      methodology: arv.methodology_notes,
    });

    // ── Update deal_score on lead ─────────────────────────────────────────────
    const dealScore = computeDealScore(arv.confidence, arv.comp_count_used ?? 0);
    await supabase
      .from('leads')
      .update({ deal_score: dealScore })
      .eq('id', lead_id);

    // ── Fire rental-yield asynchronously ─────────────────────────────────────
    fetch(`${SUPABASE_URL}/functions/v1/rental-yield`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${ANON_KEY}`,
      },
      body: JSON.stringify({
        lead_id,
        zip:     subject.zip,
        beds:    subject.beds,
        arv_mid: arv.arv_mid,
      }),
    }).catch(() => { /* fire-and-forget */ });

    return new Response(JSON.stringify(arv), {
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
