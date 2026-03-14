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
      deal_id,
      property_address,
      contract_price,
      buyer_price,
      arv,
      repair_estimate,
      property_type,
      bedrooms,
      bathrooms,
      zip_code,
      closing_date,
    } = await req.json();

    const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY');
    const SUPABASE_URL = Deno.env.get('SUPABASE_URL');
    const SUPABASE_SERVICE_ROLE_KEY = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');

    if (!ANTHROPIC_API_KEY) throw new Error('ANTHROPIC_API_KEY not set');
    if (!SUPABASE_URL || !SUPABASE_SERVICE_ROLE_KEY) throw new Error('Supabase env not set');

    // Query matching buyers from database
    let buyersUrl = `${SUPABASE_URL}/rest/v1/buyers?active=eq.true&select=*`;
    const buyersRes = await fetch(buyersUrl, {
      headers: {
        'apikey': SUPABASE_SERVICE_ROLE_KEY,
        'Authorization': `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
      },
    });
    const allBuyers = await buyersRes.json();

    // Filter buyers by buy-box criteria
    const matchedBuyers = allBuyers.filter((b: any) => {
      if (contract_price && b.max_price && contract_price > b.max_price) return false;
      if (contract_price && b.min_price && contract_price < b.min_price) return false;
      if (b.target_zips && b.target_zips.length > 0 && zip_code && !b.target_zips.includes(zip_code)) return false;
      if (b.property_types && b.property_types.length > 0 && property_type && !b.property_types.includes(property_type)) return false;
      return true;
    });

    const buyersJson = JSON.stringify(matchedBuyers.slice(0, 20));

    const prompt = `You are a wholesale real estate disposition specialist.

Deal for Assignment:
- Address: ${property_address}
- Contract Price (your cost): $${contract_price || 'unknown'}
- Asking Price to Buyers: $${buyer_price || 'unknown'}
- ARV: $${arv || 'unknown'}
- Repairs: $${repair_estimate || 'unknown'}
- Property Type: ${property_type || 'SFR'}
- Beds/Baths: ${bedrooms || '?'}/${bathrooms || '?'}
- Zip Code: ${zip_code || 'unknown'}
- Closing Date: ${closing_date || 'TBD'}

Matched Buyers from Database:
${buyersJson}

Rank these buyers 1-N based on fit. For each buyer provide:
- fit_score (0-100)
- fit_reason (1-2 sentences)
- personalization_tip (specific outreach tip for this buyer)

Also write:
- blast_email_subject: compelling subject line
- blast_email_body: 100-150 word email for all buyers
- blast_sms: max 160 characters

Return this exact JSON format:
{
  "ranked_buyers": [
    {
      "buyer": { (copy the buyer object here) },
      "fit_score": number,
      "fit_reason": "string",
      "personalization_tip": "string"
    }
  ],
  "blast_email_subject": "string",
  "blast_email_body": "string",
  "blast_sms": "string"
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
        max_tokens: 4096,
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
      await fetch(`${SUPABASE_URL}/rest/v1/ai_agent_log`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'apikey': SUPABASE_SERVICE_ROLE_KEY,
          'Authorization': `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
        },
        body: JSON.stringify({
          agent_type: 'buyer_matcher',
          deal_id: deal_id || null,
          input_data: { property_address, contract_price, zip_code, matched_count: matchedBuyers.length },
          output_data: { ranked_count: result.ranked_buyers?.length },
          tokens_used: data.usage?.input_tokens + data.usage?.output_tokens,
          duration_ms: duration,
        }),
      });
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
