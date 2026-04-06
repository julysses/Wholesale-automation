import { useState } from 'react';
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { claudeAdvisor } from '@/lib/fb-ads/claudeAdvisor';
import {
  TIER1_SIGNALS, TIER2_SIGNALS, TIER3_SIGNALS,
  SEGMENT_HEADLINES, SEGMENT_COPY_A, SEGMENT_COPY_B, SEGMENT_COPY_C,
  SEGMENT_LABELS, RETARGETING_CADENCE, KPI_THRESHOLDS,
  LOOKALIKE_BUDGET_SHIFT_PCT, CAMPAIGN_RULES, type Segment,
} from '@/lib/fb-ads/battlePlanRules';
import { ROUTING_MAP } from '@/lib/fb-ads/segmentRouter';

const SEGMENTS = Object.keys(SEGMENT_LABELS) as Segment[];

interface SectionProps {
  title: string;
  children: React.ReactNode;
  contentText: string;
}

function LibrarySection({ title, children, contentText }: SectionProps) {
  const [open, setOpen] = useState(false);
  const [explanation, setExplanation] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const explain = async () => {
    if (explanation) { setExplanation(null); return; }
    setLoading(true);
    try {
      const text = await claudeAdvisor.explainSection(title, contentText);
      setExplanation(text);
    } catch {
      setExplanation('Unable to load explanation. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-5 py-4 bg-gray-50 hover:bg-gray-100 transition-colors"
      >
        <span className="font-semibold text-gray-900 text-sm">{title}</span>
        {open ? <ChevronDown className="h-4 w-4 text-gray-500" /> : <ChevronRight className="h-4 w-4 text-gray-500" />}
      </button>
      {open && (
        <div className="p-5 space-y-4">
          {children}

          {/* Claude explain button */}
          <div className="border-t pt-4">
            <button
              onClick={explain}
              disabled={loading}
              className="flex items-center gap-2 text-xs font-medium text-[#0A1628] hover:text-[#0a1628]/70 transition-colors"
            >
              {loading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : '✦'}
              {loading ? 'Claude is thinking…' : explanation ? 'Hide explanation' : 'Claude, explain this'}
            </button>
            {explanation && (
              <div className="mt-3 p-4 bg-[#0A1628]/5 border border-[#0A1628]/15 rounded-lg text-sm text-gray-800 leading-relaxed">
                {explanation}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export function BattlePlanLibrary() {
  return (
    <div className="space-y-3">
      <div className="mb-4">
        <h2 className="font-semibold text-gray-900">Battle Plan Reference Library</h2>
        <p className="text-xs text-gray-500">Full approved Facebook Ads strategy — click any section to expand, then ask Claude to explain the rationale.</p>
      </div>

      {/* 1. Campaign Settings */}
      <LibrarySection title="1. Campaign Settings Reference" contentText="Facebook campaign settings for motivated seller real estate ads in DFW Texas.">
        <table className="w-full text-sm">
          <thead><tr className="text-xs text-gray-500 border-b"><th className="text-left py-1.5">Setting</th><th className="text-left py-1.5">Value</th><th className="text-left py-1.5">Rule</th></tr></thead>
          <tbody className="divide-y divide-gray-50">
            {[
              ['Objective', 'Leads', 'Locked — lead generation only'],
              ['Special Ad Category', 'Housing — ON', 'Legally required, cannot disable'],
              ['Daily Budget', `$${CAMPAIGN_RULES.MIN_DAILY_BUDGET}–$${CAMPAIGN_RULES.MAX_DAILY_BUDGET}`, 'Battle plan range for algorithm learning'],
              ['A/B Testing', 'ON (recommended)', 'Identify top creatives faster'],
              ['Placements', 'Feed + Marketplace + Instagram', 'Audience Network: OFF'],
            ].map(([s, v, r]) => (
              <tr key={s}><td className="py-2 font-medium text-gray-800">{s}</td><td className="py-2 text-gray-700">{v}</td><td className="py-2 text-gray-500 text-xs">{r}</td></tr>
            ))}
          </tbody>
        </table>
      </LibrarySection>

      {/* 2. Targeting Signal Matrix */}
      <LibrarySection title="2. Full Targeting Signal Matrix" contentText="Three tiers of Facebook interest targeting for motivated seller acquisition in DFW.">
        <div className="space-y-3">
          {[
            { tier: 'Tier 1 — Distress Signals', signals: TIER1_SIGNALS, color: 'red' as const },
            { tier: 'Tier 2 — Transition Signals', signals: TIER2_SIGNALS, color: 'orange' as const },
            { tier: 'Tier 3 — Landlord Burnout', signals: TIER3_SIGNALS, color: 'yellow' as const },
          ].map(({ tier, signals, color }) => (
            <div key={tier}>
              <h4 className={cn('text-xs font-bold uppercase tracking-wide mb-2',
                color === 'red' ? 'text-red-600' : color === 'orange' ? 'text-orange-600' : 'text-yellow-600'
              )}>{tier}</h4>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1">
                {signals.map(s => (
                  <div key={s.id} className="flex items-center gap-1.5 text-xs text-gray-700">
                    <span className={cn('h-1.5 w-1.5 rounded-full shrink-0',
                      color === 'red' ? 'bg-red-400' : color === 'orange' ? 'bg-orange-400' : 'bg-yellow-400'
                    )} />
                    {s.label}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </LibrarySection>

      {/* 3. Segment Headline Library */}
      <LibrarySection title="3. Segment Headline Library" contentText="Approved ad headlines for each of 8 DFW motivated seller segments with A/B/C copy variants.">
        <div className="space-y-4">
          {SEGMENTS.map(seg => (
            <div key={seg} className="border border-gray-100 rounded-lg p-3">
              <p className="text-xs font-bold text-[#0A1628] uppercase tracking-wide mb-2">{SEGMENT_LABELS[seg]}</p>
              <p className="text-sm font-semibold text-gray-900 mb-2">{SEGMENT_HEADLINES[seg]}</p>
              <div className="space-y-1.5">
                {[
                  { v: 'A', text: SEGMENT_COPY_A[seg] },
                  { v: 'B', text: SEGMENT_COPY_B[seg] },
                  { v: 'C', text: SEGMENT_COPY_C[seg] },
                ].map(({ v, text }) => (
                  <div key={v} className="text-xs text-gray-600">
                    <span className="font-semibold text-gray-800">Version {v}: </span>{text}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </LibrarySection>

      {/* 4. Creative Specs */}
      <LibrarySection title="4. Visual Creative Specs & Guidelines" contentText="Image and video specifications for Facebook motivated seller ads.">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
          {[
            ['Image size', 'Min 1200px wide, JPG/PNG'],
            ['Text overlay', 'Under 20% of image area'],
            ['Brand palette', 'Navy (#0A1628) + white + gold (#F5A623)'],
            ['Imagery', 'No smiling agents, no luxury homes, real DFW neighborhoods'],
            ['Video length', '15–30 seconds'],
            ['Video aspect', '9:16 or 1:1 (mobile-first)'],
            ['Video CTA', 'Appear in final 5 seconds'],
            ['Captions', 'Open captions required (85% watch silent)'],
          ].map(([k, v]) => (
            <div key={k} className="flex gap-2">
              <span className="font-medium text-gray-700 shrink-0">{k}:</span>
              <span className="text-gray-600">{v}</span>
            </div>
          ))}
        </div>
      </LibrarySection>

      {/* 5. Lead Form Structure */}
      <LibrarySection title="5. Lead Form Structure" contentText="Required fields for Meta Instant Lead Form for motivated seller qualification.">
        <ol className="space-y-2 text-sm">
          {[
            { name: 'Property Address', detail: 'Free text entry' },
            { name: 'Property Condition', detail: 'Good / Fair / Needs Work / Major Repairs' },
            { name: 'Situation (multi-select)', detail: 'Foreclosure / Probate / Divorce / Behind on Taxes / Tired Landlord / Relocating / Inherited / Other' },
            { name: 'Timeline', detail: 'ASAP / 1–3 Months / Just Exploring' },
            { name: 'Contact Preference', detail: 'Call / Text' },
          ].map((f, i) => (
            <li key={i} className="flex gap-3">
              <span className="h-5 w-5 bg-[#0A1628] text-white text-xs font-bold rounded-full flex items-center justify-center shrink-0">{i + 1}</span>
              <div><span className="font-medium text-gray-800">{f.name}</span><span className="text-gray-500 ml-1">— {f.detail}</span></div>
            </li>
          ))}
        </ol>
      </LibrarySection>

      {/* 6. Routing Map */}
      <LibrarySection title="6. Routing Map" contentText="How Facebook lead form situations route to WholesaleOS pipeline segments and Twilio sequences.">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr className="bg-[#0A1628] text-white"><th className="px-3 py-2 text-left rounded-tl-lg">Situation</th><th className="px-3 py-2 text-left">Segment</th><th className="px-3 py-2 text-left rounded-tr-lg">Twilio Sequence</th></tr></thead>
            <tbody>
              {ROUTING_MAP.map((r: typeof ROUTING_MAP[number], i: number) => (
                <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                  <td className="px-3 py-2 font-medium text-gray-800">{r.situations}</td>
                  <td className="px-3 py-2"><span className="bg-[#0A1628]/10 text-[#0A1628] px-2 py-0.5 rounded text-xs font-semibold">{r.segment}</span></td>
                  <td className="px-3 py-2 text-gray-600">{r.twilioSequence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </LibrarySection>

      {/* 7. Retargeting Cadence */}
      <LibrarySection title="7. Retargeting Sequence (Day 1/3/7/14/30)" contentText="The approved retargeting cadence for Facebook motivated seller campaign audiences.">
        <div className="space-y-2">
          {RETARGETING_CADENCE.map(({ day, action, audience }) => (
            <div key={day} className="flex gap-4 p-3 bg-gray-50 rounded-lg">
              <span className="h-7 w-7 bg-[#F5A623] text-white text-xs font-bold rounded-full flex items-center justify-center shrink-0">D{day}</span>
              <div>
                <p className="text-sm font-medium text-gray-800">{action}</p>
                <p className="text-xs text-gray-500">Audience: {audience}</p>
              </div>
            </div>
          ))}
        </div>
      </LibrarySection>

      {/* 8. KPI Targets */}
      <LibrarySection title="8. KPI Targets & Optimization Rules" contentText="Battle plan KPI thresholds and automated optimization triggers.">
        <div className="space-y-2 text-sm">
          {[
            { trigger: `CPL > $${KPI_THRESHOLDS.CPL_WARNING} for 5+ days`, action: 'Flag for creative rotation — CPL above battle plan threshold' },
            { trigger: `Frequency > ${KPI_THRESHOLDS.FREQUENCY_WARNING}`, action: 'Audience fatigue — rotate creative or expand audience' },
            { trigger: `Contact rate < ${KPI_THRESHOLDS.CONTACT_RATE_MIN}%`, action: 'Review Twilio timing — battle plan requires < 60 sec first touch' },
            { trigger: `${KPI_THRESHOLDS.LOOKALIKE_TRIGGER} leads accumulated`, action: `Shift ${LOOKALIKE_BUDGET_SHIFT_PCT}% of budget to Lookalike audience` },
          ].map(({ trigger, action }) => (
            <div key={trigger} className="flex gap-3 p-3 bg-amber-50 border border-amber-100 rounded-lg">
              <AlertIcon />
              <div><p className="font-medium text-gray-800">{trigger}</p><p className="text-gray-600 text-xs mt-0.5">{action}</p></div>
            </div>
          ))}
        </div>
      </LibrarySection>

      {/* 9. Lookalike Build Sequence */}
      <LibrarySection title="9. Lookalike Build Sequence" contentText="How to build and scale lookalike audiences from seed data for DFW motivated sellers.">
        <ol className="space-y-2 text-sm text-gray-700 list-decimal list-inside">
          <li>Upload custom audience CSV (Pre-Foreclosure, Probate, etc.) — min 100 records</li>
          <li>Run cold targeting for 30–45 days to accumulate lead volume</li>
          <li>At 50 form completions → enable Lookalike 1% DFW from lead audience</li>
          <li>Shift 60% of budget to Lookalike, keep 40% on proven cold creatives</li>
          <li>At 200 completions → test Lookalike 2% and 3% tiers</li>
          <li>Upload closed deal contacts quarterly for "best buyer" lookalikes</li>
        </ol>
      </LibrarySection>

      {/* 10. CAPI Setup */}
      <LibrarySection title="10. CAPI Setup Checklist" contentText="Meta Conversions API setup for privacy-first lead tracking in Facebook Ads.">
        <div className="space-y-2">
          {[
            'Install Meta Pixel on WholesaleOS lead form page (/form/*)',
            'Enable Conversions API in Facebook Events Manager',
            'Set up server-side Lead event from Supabase Edge Function',
            'Configure CAPI token in Events Manager → Datasets',
            'Add CAPI_ACCESS_TOKEN to Supabase secrets',
            'Verify event deduplication (dedup_key = leadgen_id)',
            'Test with Events Manager Test Events tool',
            'Enable auto-advanced matching (email + phone hashing)',
          ].map((item, i) => (
            <div key={i} className="flex items-start gap-2.5 text-sm text-gray-700">
              <div className="h-5 w-5 border-2 border-gray-300 rounded mt-0.5 shrink-0 flex items-center justify-center">
                <span className="text-xs text-gray-400">{i + 1}</span>
              </div>
              {item}
            </div>
          ))}
        </div>
      </LibrarySection>
    </div>
  );
}

function AlertIcon() {
  return (
    <svg className="h-4 w-4 text-amber-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
    </svg>
  );
}
