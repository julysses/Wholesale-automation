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
      ai_qualification_summary,
      motivation_tag,
      asking_price,
      mao,
      arv,
      repair_estimate,
    } = await req.json();

    const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY');
    if (!ANTHROPIC_API_KEY) throw new Error('ANTHROPIC_API_KEY not set');

    const prompt = `You are an expert wholesale real estate negotiator in the DFW Texas market.

Property: ${property_address}
Seller Situation: ${ai_qualification_summary || 'Not yet qualified'}
Seller Motivation: ${motivation_tag || 'unknown'}
Seller's Asking Price: $${asking_price || 'unknown'}
Our MAO: $${mao || 'not calculated'}
ARV: $${arv || 'not calculated'}
Repair Estimate: $${repair_estimate || 'not calculated'}

Generate 3 offer options to present to this seller. Each should be strategically crafted for their specific situation and motivation level.

For each option provide:
- Option name (e.g., "Quick Cash Close")
- Offer price (number)
- Close timeline (e.g., "14 days", "30 days")
- Key selling points for THIS seller (array of 2-3 short strings)
- How to present it verbally (1-2 sentence pitch)

Also provide:
- Top 2 likely objections from this seller
- Word-for-word response script for each objection

Also provide a brief recommendation field (2-3 sentences about the overall deal).

Respond in this exact JSON format:
{
  "options": [
    {
      "name": "string",
      "offer_price": number,
      "close_timeline": "string",
      "selling_points": ["string", "string"],
      "pitch": "string"
    }
  ],
  "objections": [
    {
      "objection": "string",
      "script": "string"
    }
  ],
  "recommendation": "string"
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
        max_tokens: 2048,
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

    // Log
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
            agent_type: 'offer_generator',
            lead_id: lead_id || null,
            input_data: { property_address, arv, repair_estimate, mao },
            output_data: result,
            tokens_used: data.usage?.input_tokens + data.usage?.output_tokens,
            duration_ms: duration,
          }),
        });
      }
    } catch (_) { /* ignore */ }

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
