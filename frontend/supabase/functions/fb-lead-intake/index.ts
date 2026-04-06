/**
 * Supabase Edge Function: fb-lead-intake
 *
 * Receives POST webhook from Meta Lead Ads (or direct test POSTs).
 * Parses situations[], routes to segment, creates fb_lead record,
 * fires Twilio SMS within 60 seconds.
 *
 * Deploy: supabase functions deploy fb-lead-intake
 * Secrets: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY,
 *          TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER
 */

import { serve } from 'https://deno.land/std@0.168.0/http/server.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const corsHeaders = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, x-client-info, apikey, content-type, x-hub-signature-256',
};

// ── Situation → Segment routing ────────────────────────────────────────────────
function routeSituations(situations: string[], timeline?: string): string {
  const lower = situations.map(s => s.toLowerCase());
  if (lower.includes('foreclosure')) return 'HOT-URGENT';
  if (lower.includes('behind on taxes')) return 'HOT-TAX';
  if (lower.includes('probate') || lower.includes('inherited')) return 'HOT-ESTATE';
  if (lower.includes('divorce')) return 'HOT-LEGAL';
  if (lower.includes('tired landlord')) return 'WARM-LANDLORD';
  if (lower.includes('relocating')) return 'WARM-RELOCATION';
  if (timeline?.toLowerCase() === 'just exploring') return 'COLD-NURTURE';
  return 'COLD-NURTURE';
}

// ── Twilio SMS ─────────────────────────────────────────────────────────────────
async function sendSMS(to: string, body: string): Promise<boolean> {
  const accountSid = Deno.env.get('TWILIO_ACCOUNT_SID');
  const authToken = Deno.env.get('TWILIO_AUTH_TOKEN');
  const fromNumber = Deno.env.get('TWILIO_FROM_NUMBER');
  if (!accountSid || !authToken || !fromNumber) return false;

  const url = `https://api.twilio.com/2010-04-01/Accounts/${accountSid}/Messages.json`;
  const credentials = btoa(`${accountSid}:${authToken}`);
  const params = new URLSearchParams({ To: to, From: fromNumber, Body: body });

  try {
    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Basic ${credentials}`,
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: params.toString(),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

// ── Main handler ───────────────────────────────────────────────────────────────
serve(async (req) => {
  if (req.method === 'OPTIONS') {
    return new Response('ok', { headers: corsHeaders });
  }

  try {
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const serviceKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(supabaseUrl, serviceKey);

    const body = await req.json();

    // Support both direct POST and Facebook Lead Ads webhook format
    let leads: any[] = [];
    if (body.entry) {
      // Facebook webhook format: entry[].changes[].value
      for (const entry of body.entry || []) {
        for (const change of entry.changes || []) {
          if (change.field === 'leadgen') {
            leads.push(change.value);
          }
        }
      }
    } else {
      // Direct POST (test or manual) — body is a single lead
      leads = [body];
    }

    const results = [];

    for (const lead of leads) {
      const {
        name,
        phone,
        email,
        property_address,
        condition,
        situations = [],
        timeline,
        contact_preference,
        campaign_id: externalCampaignId,
        ad_set_id: externalAdSetId,
      } = lead;

      const situationsArray = Array.isArray(situations)
        ? situations
        : typeof situations === 'string'
        ? situations.split(',').map((s: string) => s.trim())
        : [];

      const segmentTag = routeSituations(situationsArray, timeline);

      // Look up internal campaign by external ID
      let internalCampaignId: string | null = null;
      let internalAdSetId: string | null = null;
      if (externalCampaignId) {
        const { data } = await supabase
          .from('fb_campaigns')
          .select('id')
          .eq('wizard_state->step1->>name', externalCampaignId)
          .limit(1)
          .single();
        internalCampaignId = data?.id || null;
      }

      // Insert fb_lead record
      const { data: insertedLead, error: leadError } = await supabase
        .from('fb_leads')
        .insert({
          campaign_id: internalCampaignId,
          ad_set_id: internalAdSetId,
          name,
          phone,
          email,
          property_address,
          condition,
          situations: situationsArray,
          timeline,
          contact_preference,
          segment_tag: segmentTag,
          twilio_sms_sent: false,
          contacted: false,
          appointment_set: false,
        })
        .select()
        .single();

      if (leadError) {
        console.error('Lead insert error:', leadError);
        results.push({ error: leadError.message });
        continue;
      }

      const leadId = insertedLead.id;

      // Fire SMS and create main pipeline lead in parallel
      const isHot = segmentTag.startsWith('HOT');
      const smsPromise = (async () => {
        if (!phone) return false;
        const firstName = (name || '').split(' ')[0] || 'there';
        const smsBody = `Hi ${firstName}, thanks for reaching out. We received your info on ${property_address || 'your property'}. Someone from our team will call you shortly — or reply here if you prefer to text.`;
        const sent = await sendSMS(phone, smsBody);
        if (sent) {
          await supabase
            .from('fb_leads')
            .update({ twilio_sms_sent: true, twilio_sms_time: new Date().toISOString() })
            .eq('id', leadId);
        }
        return sent;
      })();

      const pipelinePromise = supabase.from('leads').insert({
        property_address: property_address || 'Unknown',
        owner_first_name: (name || '').split(' ')[0],
        owner_last_name: (name || '').split(' ').slice(1).join(' '),
        owner_phone_1: phone,
        owner_email: email,
        source: 'facebook_lead_ad',
        inbound_channel: 'facebook_lead_ad',
        status: 'new',
        motivation_tag: situationsArray[0] || 'Other',
        score_motivation: isHot ? 3 : 2,
        score_timeline: timeline === 'ASAP' ? 3 : timeline === '1–3 Months' ? 2 : 1,
        score_equity: 2,
        score_condition: condition === 'Major Repairs' ? 3 : condition === 'Needs Work' ? 2 : 1,
        score_flexibility: 2,
        priority_tier: isHot ? 'A' : segmentTag.startsWith('WARM') ? 'B' : 'C',
        contact_attempts: 0,
        sms_sequence_active: false,
        email_sequence_active: false,
        dnc: false,
      });

      const [smsSent] = await Promise.all([smsPromise, pipelinePromise]);

      results.push({ lead_id: leadId, segment_tag: segmentTag, sms_sent: smsSent });
    }

    return new Response(JSON.stringify({ success: true, processed: results.length, results }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 200,
    });

  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error('fb-lead-intake error:', msg);
    return new Response(JSON.stringify({ error: msg }), {
      headers: { ...corsHeaders, 'Content-Type': 'application/json' },
      status: 500,
    });
  }
});
