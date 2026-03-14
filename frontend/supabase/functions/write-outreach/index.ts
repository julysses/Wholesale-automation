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
      city,
      owner_first_name,
      motivation_tag,
      contact_attempts,
      channel,
      tone,
    } = await req.json();

    const ANTHROPIC_API_KEY = Deno.env.get('ANTHROPIC_API_KEY');
    if (!ANTHROPIC_API_KEY) throw new Error('ANTHROPIC_API_KEY not set');

    const prompt = `You are a direct response copywriter specializing in motivated seller outreach for real estate.

Write ${channel} outreach copy for this lead:

Property Address: ${property_address}
City: ${city}
Owner Name: ${owner_first_name || 'Homeowner'}
Motivation Tag: ${motivation_tag || 'not specified'}
Contact Attempt #: ${contact_attempts || 1}
Tone: ${tone}

Rules:
- SMS: Max 160 characters, conversational, no slang, one clear CTA
- Email: Subject line + body under 150 words, personal, not salesy
- Voicemail: 30-45 second script, friendly, clear callback ask
- Direct Mail: 3-4 sentences for a handwritten-style note

Generate 3 variations. Return JSON with this exact format:
[
  {
    "channel": "${channel}",
    "subject": "string (only for email, null for others)",
    "body": "string",
    "estimated_response_rate_notes": "string (brief note on why this variation might work)"
  }
]

Only output valid JSON array, no other text.`;

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
            agent_type: 'outreach_writer',
            lead_id: lead_id || null,
            input_data: { channel, tone, contact_attempts },
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
