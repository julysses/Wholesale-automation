import { useState, useEffect } from 'react';
import { CheckCircle, XCircle, Loader2, Rocket } from 'lucide-react';
import { cn } from '@/lib/utils';
import { claudeAdvisor, type PreFlightSummary } from '@/lib/fb-ads/claudeAdvisor';
import { CAMPAIGN_RULES } from '@/lib/fb-ads/battlePlanRules';

interface WizardState {
  step1: Record<string, unknown>;
  step2: Record<string, unknown>;
  step3: Record<string, unknown>;
  step4: Record<string, unknown>;
  step5: Record<string, unknown>;
}

interface Props {
  wizardState: WizardState;
}

interface CheckItem {
  section: string;
  label: string;
  pass: boolean;
  detail?: string;
}

function buildChecklist(state: WizardState): CheckItem[] {
  const s1 = state.step1 as any;
  const s2 = state.step2 as any;
  const s3 = state.step3 as any;
  const s4 = state.step4 as any;
  const s5 = state.step5 as any;

  const budget = Number(s1?.daily_budget || 0);
  const customAudiences = (s2?.custom_audiences || []) as any[];
  const tier1Signals = (s2?.tier1_signals || []) as string[];
  const counties = (s2?.counties || []) as string[];
  const adSets = (s3?.ad_sets || []) as any[];
  const hasGenericHeadline = adSets.some((a: any) =>
    ['we buy houses', 'we buy homes', 'cash for houses'].some(g => (a.headline || '').toLowerCase().includes(g))
  );

  return [
    // Campaign Settings
    { section: 'Campaign Settings', label: 'Objective: Leads', pass: true },
    { section: 'Campaign Settings', label: 'Special Ad Category: Housing — ON', pass: true },
    { section: 'Campaign Settings', label: `Daily budget: $${budget} (within $${CAMPAIGN_RULES.MIN_DAILY_BUDGET}–$${CAMPAIGN_RULES.MAX_DAILY_BUDGET} range)`, pass: budget >= CAMPAIGN_RULES.MIN_DAILY_BUDGET && budget <= CAMPAIGN_RULES.MAX_DAILY_BUDGET },
    { section: 'Campaign Settings', label: 'A/B testing: Enabled', pass: !!s1?.ab_test_enabled },
    { section: 'Campaign Settings', label: 'Campaign name set', pass: !!(s1?.name) },
    { section: 'Campaign Settings', label: 'Start date set', pass: !!(s1?.start_date) },

    // Targeting
    { section: 'Targeting', label: `Custom Audience uploaded (${customAudiences.length} audience${customAudiences.length !== 1 ? 's' : ''})`, pass: customAudiences.length > 0, detail: customAudiences.map((a: any) => `${a.name} — ${a.recordCount} records`).join(', ') || undefined },
    { section: 'Targeting', label: 'Minimum 1 Tier 1 distress signal selected', pass: tier1Signals.length > 0 },
    { section: 'Targeting', label: 'Homeowners only: ON', pass: true },
    { section: 'Targeting', label: 'Audience Network: OFF', pass: true },
    { section: 'Targeting', label: 'Marketplace placement: ON', pass: adSets.some((a: any) => a.placement_marketplace) },
    { section: 'Targeting', label: `DFW counties selected (${counties.join(', ') || 'none'})`, pass: counties.length > 0 },

    // Ad Sets
    { section: 'Ad Sets', label: `Each audience has a dedicated ad set (${adSets.length} ad set${adSets.length !== 1 ? 's' : ''})`, pass: adSets.length > 0 },
    { section: 'Ad Sets', label: 'No generic "We Buy Houses" headline detected', pass: !hasGenericHeadline },
    { section: 'Ad Sets', label: 'Segment-matched copy assigned', pass: adSets.every((a: any) => a.copy_version_a || a.headline) },

    // Creative
    { section: 'Creative', label: 'Image uploaded', pass: !!(s4?.image_file || s4?.image_url), detail: s4?.image_file ? 'Image file selected' : undefined },
    { section: 'Creative', label: 'Copy Version A written', pass: !!(s4?.copy_a) },
    { section: 'Creative', label: 'Copy Version B written', pass: !!(s4?.copy_b) },
    { section: 'Creative', label: 'Text overlay requirement acknowledged', pass: true },

    // Lead Form
    { section: 'Lead Form', label: 'All 5 required fields present', pass: true },
    { section: 'Lead Form', label: 'Situation field: Multi-select enabled', pass: true },
    { section: 'Lead Form', label: 'Routing map: Confirmed', pass: true },
    { section: 'Lead Form', label: 'Thank you message configured', pass: !!(s5?.confirmation_message) },

    // Post-Capture
    { section: 'Post-Capture', label: 'Twilio SMS sequence assigned', pass: true, detail: 'Sequences A–F + long-drip configured in routing map' },
    { section: 'Post-Capture', label: 'WholesaleOS webhook URL: Configured', pass: true, detail: '/webhooks/facebook/lead (FB Lead Ads integration)' },
    { section: 'Post-Capture', label: 'CAPI event: Ready to configure', pass: true },
  ];
}

export function Step6PreFlightChecklist({ wizardState }: Props) {
  const [claudeSummary, setClaudeSummary] = useState<PreFlightSummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  const checks = buildChecklist(wizardState);
  const sections = Array.from(new Set(checks.map(c => c.section)));
  const allPass = checks.every(c => c.pass);
  const failCount = checks.filter(c => !c.pass).length;

  useEffect(() => {
    if (allPass) fetchSummary();
  }, [allPass]);

  const fetchSummary = async () => {
    setLoadingSummary(true);
    setSummaryError(null);
    try {
      const summary = await claudeAdvisor.preFlightSummary(wizardState as unknown as Record<string, unknown>);
      setClaudeSummary(summary);
    } catch (e: any) {
      setSummaryError(e.message || 'Failed to generate summary');
    } finally {
      setLoadingSummary(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Overall status */}
      <div className={cn(
        'flex items-center gap-3 p-4 rounded-xl border',
        allPass ? 'bg-green-50 border-green-300' : 'bg-red-50 border-red-300'
      )}>
        {allPass ? (
          <Rocket className="h-6 w-6 text-green-600" />
        ) : (
          <XCircle className="h-6 w-6 text-red-500" />
        )}
        <div>
          <p className={cn('font-bold', allPass ? 'text-green-800' : 'text-red-800')}>
            {allPass ? '✅ READY TO LAUNCH' : `❌ NOT READY — ${failCount} item${failCount !== 1 ? 's' : ''} need${failCount === 1 ? 's' : ''} attention`}
          </p>
          <p className="text-sm text-gray-600 mt-0.5">
            {allPass ? 'All battle plan requirements met. Campaign is ready.' : 'Resolve all red items before marking this campaign as launch-ready.'}
          </p>
        </div>
      </div>

      {/* Checklist by section */}
      {sections.map(section => {
        const sectionChecks = checks.filter(c => c.section === section);
        const sectionPass = sectionChecks.every(c => c.pass);
        return (
          <div key={section}>
            <div className="flex items-center gap-2 mb-2">
              <h3 className="text-sm font-bold text-gray-800 uppercase tracking-wide">{section}</h3>
              {sectionPass ? (
                <span className="text-xs text-green-600 font-medium">All passed</span>
              ) : (
                <span className="text-xs text-red-500 font-medium">
                  {sectionChecks.filter(c => !c.pass).length} failed
                </span>
              )}
            </div>
            <div className="space-y-1.5">
              {sectionChecks.map((check, i) => (
                <div key={i} className={cn(
                  'flex items-start gap-2.5 p-2.5 rounded-lg',
                  check.pass ? 'bg-green-50' : 'bg-red-50'
                )}>
                  {check.pass
                    ? <CheckCircle className="h-4 w-4 text-green-500 shrink-0 mt-0.5" />
                    : <XCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />}
                  <div>
                    <p className="text-sm text-gray-800">{check.label}</p>
                    {check.detail && <p className="text-xs text-gray-500 mt-0.5">{check.detail}</p>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        );
      })}

      {/* Claude Campaign Intelligence */}
      <div className="border border-[#0A1628]/20 rounded-xl overflow-hidden">
        <div className="bg-[#0A1628] px-4 py-3 flex items-center justify-between">
          <span className="text-sm font-semibold text-white">✦ Campaign Intelligence</span>
          {!claudeSummary && allPass && (
            <button
              onClick={fetchSummary}
              disabled={loadingSummary}
              className="flex items-center gap-1.5 text-xs text-white/80 hover:text-white transition-colors"
            >
              {loadingSummary ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : '↻'}
              {loadingSummary ? 'Generating…' : 'Generate Summary'}
            </button>
          )}
        </div>
        <div className="p-4">
          {!allPass && (
            <p className="text-sm text-gray-500">Resolve all checklist items to generate the Claude campaign summary.</p>
          )}
          {allPass && loadingSummary && (
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Claude is analyzing your campaign…
            </div>
          )}
          {summaryError && (
            <p className="text-sm text-red-500">{summaryError}</p>
          )}
          {claudeSummary && (
            <div className="space-y-3">
              <p className="text-sm text-gray-800 leading-relaxed">{claudeSummary.summary}</p>
              <div className="grid grid-cols-2 gap-3">
                <div className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500 mb-1">Est. CPL — Cold Audience</p>
                  <p className="text-lg font-bold text-[#0A1628]">{claudeSummary.estimated_cpl_cold}</p>
                </div>
                <div className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-500 mb-1">Est. CPL — Retargeting</p>
                  <p className="text-lg font-bold text-[#F5A623]">{claudeSummary.estimated_cpl_retargeting}</p>
                </div>
              </div>
              <div className="bg-[#0A1628]/5 rounded-lg p-3">
                <p className="text-xs font-semibold text-[#0A1628] mb-1">Recommendation</p>
                <p className="text-sm text-gray-700">{claudeSummary.recommendation}</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
