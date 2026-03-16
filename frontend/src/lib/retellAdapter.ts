/**
 * Retell AI frontend adapter — TypeScript
 *
 * Provides typed wrappers for the Retell AI REST API and webhook event handling.
 * Matches the blueprint call payload structure exactly.
 *
 * Blueprint payload:
 * {
 *   "lead_id": "uuid",
 *   "phone_number": "+15551234567",
 *   "property_address": "123 Main St",
 *   "owner_name": "John Doe",
 *   "metadata": {
 *     "seller_score": 82,
 *     "distress_flags": ["vacant", "tax_delinquent"]
 *   }
 * }
 *
 * Functions:
 *   initializeAgent()       — configure agent with API key
 *   createCall()            — initiate outbound AI call
 *   updateCallStatus()      — refresh call state from Retell API
 *   receiveWebhookEvent()   — normalize raw Retell webhook payload
 *   parseTranscript()       — convert transcript to structured turns
 *   extractLeadSignals()    — POST to /api/qualify to get qual result
 */

import axios from 'axios';

// ── Types ─────────────────────────────────────────────────────────────────────

export type CallDisposition =
  | 'no_answer'
  | 'voicemail'
  | 'wrong_number'
  | 'not_interested'
  | 'callback'
  | 'warm'
  | 'hot'
  | 'appointment_set'
  | 'unknown';

export type CallClassification = 'HOT' | 'WARM' | 'COLD';

export type RetellEventType =
  | 'call_started'
  | 'call_answered'
  | 'call_transcript'
  | 'call_ended'
  | 'call_analyzed'
  | 'retell.call.started'
  | 'retell.call.answered'
  | 'retell.call.transcript'
  | 'retell.call.completed'
  | 'retell.call.analyzed';

/** Blueprint call payload — matches Python CallRequest.to_payload() */
export interface CallPayload {
  lead_id: string;
  phone_number: string;           // E.164
  property_address: string;
  owner_name: string;
  metadata: {
    seller_score?: number;
    distress_flags?: string[];
    campaign_id?: string;
    [key: string]: unknown;
  };
}

/** Options for initiating a call */
export interface CreateCallOptions {
  leadId: string;
  phoneNumber: string;            // E.164
  propertyAddress: string;
  ownerName: string;
  agentName?: string;
  campaignId?: string;
  sellerScore?: number;
  distressFlags?: string[];
}

/** A created call record returned from the API */
export interface CallRecord {
  callId: string;
  leadId: string;
  phoneNumber: string;
  status: string;
  provider: 'retell' | 'air_ai';
  providerData?: Record<string, unknown>;
}

/** A single transcript speaker turn */
export interface TranscriptTurn {
  role: 'agent' | 'user' | 'unknown';
  content: string;
  timestampMs?: number;
}

/** Qualification signals extracted from transcript */
export interface LeadSignals {
  timeline: 'immediately' | '30_days' | '60_days' | '3_to_6_months' | 'no_timeline';
  condition: 'fully_updated' | 'minor_repairs' | 'needs_repairs' | 'major_repairs';
  occupancy: 'owner_occupied' | 'tenant_occupied' | 'vacant';
  askingPrice: number | null;
  mortgageBalance: number | null;
  sentiment: 'motivated' | 'neutral' | 'hesitant' | 'not_interested';
  qualificationScore: number;
  classification: CallClassification;
  summary: string;
  keyQuotes: string[];
  offerRangeLow: number | null;
  offerRangeHigh: number | null;
  scoreBreakdown: Record<string, number>;
}

/** Normalized Retell webhook event */
export interface RetellWebhookEvent {
  eventType: RetellEventType;
  callId: string;
  leadId: string;
  disposition?: CallDisposition;
  transcript?: TranscriptTurn[];
  rawTranscript?: string;
  durationSeconds?: number;
  recordingUrl?: string;
  isFinal: boolean;
  rawPayload: Record<string, unknown>;
}

// ── Agent state ───────────────────────────────────────────────────────────────

interface AgentConfig {
  apiKey: string;
  agentId: string;
  fromNumber: string;
  backendBaseUrl: string;   // e.g. "http://localhost:8000"
}

let _config: AgentConfig | null = null;

/**
 * Initialize the Retell adapter with credentials.
 * Must be called before createCall().
 */
export function initializeAgent(config: AgentConfig): void {
  _config = config;
}

function requireConfig(): AgentConfig {
  if (!_config) {
    throw new Error(
      'RetellAdapter not initialized. Call initializeAgent() first.'
    );
  }
  return _config;
}

// ── Core functions ─────────────────────────────────────────────────────────────

/**
 * Initiate an outbound AI call via the backend API.
 *
 * The backend (`POST /api/calls/retell`) proxies to Retell AI
 * using the server-side API key and returns the created call record.
 */
export async function createCall(options: CreateCallOptions): Promise<CallRecord> {
  const cfg = requireConfig();

  const payload: CallPayload = {
    lead_id: options.leadId,
    phone_number: options.phoneNumber,
    property_address: options.propertyAddress,
    owner_name: options.ownerName,
    metadata: {
      ...(options.sellerScore !== undefined && { seller_score: options.sellerScore }),
      ...(options.distressFlags?.length && { distress_flags: options.distressFlags }),
      ...(options.campaignId && { campaign_id: options.campaignId }),
    },
  };

  const resp = await axios.post<{
    call_id: string;
    lead_id: string;
    phone_number: string;
    status: string;
    provider: 'retell' | 'air_ai';
    provider_data?: Record<string, unknown>;
  }>(`${cfg.backendBaseUrl}/api/calls/retell`, payload);

  return {
    callId: resp.data.call_id,
    leadId: resp.data.lead_id,
    phoneNumber: resp.data.phone_number,
    status: resp.data.status,
    provider: resp.data.provider,
    providerData: resp.data.provider_data,
  };
}

/**
 * Fetch current status of a call from the backend (which queries Retell AI).
 */
export async function updateCallStatus(callId: string): Promise<{
  callId: string;
  status: string;
  disposition?: CallDisposition;
}> {
  const cfg = requireConfig();
  const resp = await axios.get<{
    call_id: string;
    call_status: string;
    disposition?: string;
  }>(`${cfg.backendBaseUrl}/api/calls/retell/${callId}`);

  return {
    callId: resp.data.call_id,
    status: resp.data.call_status,
    disposition: resp.data.disposition as CallDisposition | undefined,
  };
}

/**
 * Normalize a raw Retell webhook payload.
 * Used in the frontend webhook handler (e.g. if receiving webhooks via
 * Next.js API route or Supabase Edge Function).
 */
export function receiveWebhookEvent(
  raw: Record<string, unknown>
): RetellWebhookEvent {
  const eventType = (raw.event ?? raw.event_type ?? '') as RetellEventType;
  const callData  = (raw.call ?? {}) as Record<string, unknown>;
  const callId    = String(callData.call_id ?? '');
  const metadata  = (callData.metadata ?? {}) as Record<string, unknown>;
  const leadId    = String(metadata.lead_id ?? '');

  const FINAL_EVENTS: RetellEventType[] = [
    'call_ended', 'call_analyzed',
    'retell.call.completed', 'retell.call.analyzed',
  ];

  const rawTranscript = callData.transcript;
  const turns = rawTranscript
    ? parseTranscript(rawTranscript)
    : [];

  const analysis = (callData.call_analysis ?? {}) as Record<string, unknown>;
  const customData = (
    (analysis.custom_analysis_data ?? {}) as Record<string, unknown>
  );

  const rawDisp = String(customData.disposition ?? callData.disconnection_reason ?? '');
  const disposition = normalizeDisposition(rawDisp);

  return {
    eventType,
    callId,
    leadId,
    disposition,
    transcript: turns,
    rawTranscript: typeof rawTranscript === 'string' ? rawTranscript : undefined,
    durationSeconds: Math.floor(Number(callData.duration_ms ?? 0) / 1000),
    recordingUrl: callData.recording_url as string | undefined,
    isFinal: FINAL_EVENTS.includes(eventType),
    rawPayload: raw,
  };
}

/**
 * Parse a Retell transcript into structured turns.
 *
 * Handles:
 *   - Array of {role, content} objects (Retell v2)
 *   - Plain string with "Agent: ..." / "Seller: ..." lines
 */
export function parseTranscript(raw: unknown): TranscriptTurn[] {
  if (!raw) return [];

  // Array format
  if (Array.isArray(raw)) {
    return raw.map((item: Record<string, unknown>) => ({
      role: normalizeRole(String(item.role ?? '')),
      content: String(item.content ?? ''),
      timestampMs: item.words && Array.isArray(item.words) && item.words.length > 0
        ? Number((item.words[0] as Record<string, unknown>).start ?? 0)
        : undefined,
    }));
  }

  // Plain string
  if (typeof raw === 'string') {
    const turns: TranscriptTurn[] = [];
    for (const line of raw.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      if (/^agent:/i.test(trimmed)) {
        turns.push({ role: 'agent', content: trimmed.slice(6).trim() });
      } else if (/^(user|seller|owner):/i.test(trimmed)) {
        const colonIdx = trimmed.indexOf(':');
        turns.push({ role: 'user', content: trimmed.slice(colonIdx + 1).trim() });
      } else if (turns.length > 0) {
        turns[turns.length - 1].content += ' ' + trimmed;
      } else {
        turns.push({ role: 'unknown', content: trimmed });
      }
    }
    return turns;
  }

  return [];
}

/**
 * Send transcript to the backend qualification endpoint.
 *
 * Returns structured lead signals with qualification_score and HOT/WARM/COLD
 * classification.
 *
 * Backend route: POST /api/qualify
 */
export async function extractLeadSignals(
  transcript: TranscriptTurn[],
  propertyAddress: string,
  ownerName: string,
): Promise<LeadSignals> {
  const cfg = requireConfig();

  const text = transcript
    .map((t) => `${t.role === 'agent' ? 'Agent' : 'Seller'}: ${t.content}`)
    .join('\n');

  const resp = await axios.post<{
    timeline: string;
    condition: string;
    occupancy: string;
    asking_price: number | null;
    mortgage_balance: number | null;
    sentiment: string;
    qualification_score: number;
    classification: string;
    summary: string;
    key_quotes: string[];
    offer_range_low: number | null;
    offer_range_high: number | null;
    score_breakdown: Record<string, number>;
  }>(`${cfg.backendBaseUrl}/api/qualify`, {
    transcript: text,
    property_address: propertyAddress,
    owner_name: ownerName,
  });

  const d = resp.data;
  return {
    timeline: d.timeline as LeadSignals['timeline'],
    condition: d.condition as LeadSignals['condition'],
    occupancy: d.occupancy as LeadSignals['occupancy'],
    askingPrice: d.asking_price,
    mortgageBalance: d.mortgage_balance,
    sentiment: d.sentiment as LeadSignals['sentiment'],
    qualificationScore: d.qualification_score,
    classification: d.classification as CallClassification,
    summary: d.summary,
    keyQuotes: d.key_quotes,
    offerRangeLow: d.offer_range_low,
    offerRangeHigh: d.offer_range_high,
    scoreBreakdown: d.score_breakdown,
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const DISPOSITION_MAP: Record<string, CallDisposition> = {
  no_answer:          'no_answer',
  voicemail:          'voicemail',
  wrong_number:       'wrong_number',
  not_interested:     'not_interested',
  callback_requested: 'callback',
  callback:           'callback',
  interested:         'warm',
  warm:               'warm',
  hot_lead:           'hot',
  hot:                'hot',
  appointment_set:    'appointment_set',
  appointment:        'appointment_set',
};

function normalizeDisposition(raw: string): CallDisposition | undefined {
  if (!raw) return undefined;
  return DISPOSITION_MAP[raw.toLowerCase()] ?? 'unknown';
}

function normalizeRole(raw: string): TranscriptTurn['role'] {
  const lower = raw.toLowerCase();
  if (lower === 'agent') return 'agent';
  if (['user', 'seller', 'owner', 'human'].includes(lower)) return 'user';
  return 'unknown';
}

/**
 * Derive a human-readable label for a disposition.
 */
export function dispositionLabel(disposition: CallDisposition): string {
  const map: Record<CallDisposition, string> = {
    no_answer:       'No Answer',
    voicemail:       'Voicemail',
    wrong_number:    'Wrong Number',
    not_interested:  'Not Interested',
    callback:        'Callback Requested',
    warm:            'Warm Lead',
    hot:             'Hot Lead',
    appointment_set: 'Appointment Set',
    unknown:         'Unknown',
  };
  return map[disposition] ?? disposition;
}

/**
 * Return Tailwind color classes for a lead classification badge.
 */
export function classificationColor(classification: CallClassification): {
  bg: string; text: string; border: string;
} {
  switch (classification) {
    case 'HOT':  return { bg: 'bg-red-100',    text: 'text-red-800',    border: 'border-red-300'    };
    case 'WARM': return { bg: 'bg-orange-100', text: 'text-orange-800', border: 'border-orange-300' };
    case 'COLD': return { bg: 'bg-gray-100',   text: 'text-gray-600',   border: 'border-gray-300'   };
  }
}
