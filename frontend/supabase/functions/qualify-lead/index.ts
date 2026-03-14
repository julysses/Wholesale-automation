import { serve } from 'https://deno.land/std@0.168.0/http/server.ts';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type',
};

serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const {
      lead_id,
      property_address,
      seller_notes,
      estimated_equity_pct,
    } = await req.json();

    const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY');
    if (!ANTHROPIC_API_KEY) throw new Error('ANTHROPIC_API_KEY not set');

    const prompt = `You are an expert real estate acquisitions analyst specializing in wholesale deals. Analyze the following seller conversation and score the lead on 5 factors.

Property: ${property_address}
Seller Notes / Transcript: ${seller_notes || 'No notes provided yet.'}

Score each factor from 1-3:
1. MOTIVATION (1=no urgency, 2=moderate, 3=must sell now)
2. TIMELINE (1=6+ months, 2=30-90 days, 3=under 30 days)
3. EQUITY (1=under 30%, 2=30-59%, 3=60%+) — use this estimate: ${estimated_equity_pct || 'unknown'}%
4. CONDITION (1=major structural, 2=moderate repairs, 3=cosmetic/good)
5. FLEXIBILITY (1=fixed on retail, 2=somewhat flexible, 3=open to cash/as-is)

Respond in this exact JSON format:
{
  "score_motivation": <1-3>,
  "score_timeline": <1-3>,
  "score_equity": <1-3>,
  "score_condition": <1-3>,
  "score_flexibility": <1-3>,
  "total_score": <5-15>,
  "tier": "HOT" or "WARM" or "COLD",
  "qualification_summary": "<2-3 sentence summary of seller situation>",
  "recommended_next_action": "<specific next step>",
  "key_risks": ["<risk 1>", "<risk 2>"]
}

Only output valid JSON, no other text.`;

    const startTime = Date.now();

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-5',
        max_tokens: 1024,
        messages: [{ role: 'user', content: prompt }],
      }),
    });

    const duration = Date.now() - startTime;
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error?.message || 'Claude API error');
    }

    const text = data.content[0].text;
    const result = JSON.parse(text);
    result.tier = result.total_score >= 13 ? 'HOT' : result.total_score >= 8 ? 'WARM' : 'COLD';

    // Log to Supabase
    try {
      const SUPABASE_URL = Deno.env.get('SUPABASE_URL');
      const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
      if (SUPABASE_URL && SUPABASE_SERVICE_ROLE_KEY) {
        await fetch(`${SUPABASE_URL}/rest/v1/ai_agent_log`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'apikey': SUPABASE_SERVICE_ROLE_KEY,
            'Authorization': `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
          },
          body: JSON.stringify({
            agent_type: 'lead_qualifier',
            lead_id: lead_id || null,
            input_data: { property_address, seller_notes, estimated_equity_pct },
            output_data: result,
            tokens_used: data.usage?.input_tokens + data.usage?.output_tokens,
            duration_ms: duration,
          }),
        });
      }
    } catch (_) { /* ignore logging errors */ }

    return new Response(JSON.stringify(result), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({ error: error instanceof Error ? error.message : 'Unknown error' }),
      { status: 500, headers: { ...corsHeaders, 'Content-Type': 'application/json' } }
    );
  }
});
