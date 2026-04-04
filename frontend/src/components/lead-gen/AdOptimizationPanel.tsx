import { useState } from 'react';
import { Sparkles, AlertTriangle, ArrowRight, Copy, Check, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

interface PauseRecommendation {
  creative_id: string;
  reason: string;
}

interface BudgetShift {
  from_campaign: string;
  to_campaign: string;
  amount: number;
  reason: string;
}

interface AdCopyVariant {
  headline: string;
  primary_text: string;
  cta: string;
  pain_point_angle: string;
  rationale: string;
}

interface OptimizationReport {
  pause_recommendations: PauseRecommendation[];
  budget_shifts: BudgetShift[];
  new_copy_angles: AdCopyVariant[];
  audience_suggestions: string[];
  summary: string;
}

const ANGLE_LABELS: Record<string, string> = {
  foreclosure: 'Foreclosure',
  divorce: 'Divorce',
  inherited: 'Inherited',
  tired_landlord: 'Tired Landlord',
  relocation: 'Relocation',
  repairs: 'Repairs',
  generic: 'Generic',
};

export function AdOptimizationPanel() {
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<OptimizationReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [generatedVariants, setGeneratedVariants] = useState<AdCopyVariant[]>([]);
  const [selectedAngle, setSelectedAngle] = useState('foreclosure');
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);

  const runAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch('/api/ai/lead-gen/optimize', { method: 'POST' });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setReport(data);
    } catch (e: any) {
      setError(e.message || 'Analysis failed');
    } finally {
      setLoading(false);
    }
  };

  const generateVariants = async () => {
    setGenerating(true);
    setError(null);
    try {
      const resp = await fetch('/api/ai/lead-gen/copy-variants', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pain_point_angle: selectedAngle, num_variants: 5 }),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const data = await resp.json();
      setGeneratedVariants(data.variants || []);
    } catch (e: any) {
      setError(e.message || 'Copy generation failed');
    } finally {
      setGenerating(false);
    }
  };

  const copyVariant = async (idx: number, variant: AdCopyVariant) => {
    const text = `HEADLINE: ${variant.headline}\n\nBODY: ${variant.primary_text}\n\nCTA: ${variant.cta}`;
    await navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Campaign Analysis Section */}
      <div className="bg-white border rounded-xl p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="font-semibold text-gray-900">Campaign Optimization Analysis</h3>
            <p className="text-xs text-gray-500 mt-0.5">Claude AI analyzes your campaigns and suggests budget shifts, pauses, and new angles</p>
          </div>
          <button
            onClick={runAnalysis}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 bg-[#1B3A5C] text-white text-sm font-medium rounded-lg hover:bg-[#162f4d] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Run Analysis
          </button>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {report && (
          <div className="space-y-4">
            {/* Summary */}
            {report.summary && (
              <div className="p-4 bg-blue-50 border border-blue-100 rounded-lg text-sm text-blue-800 leading-relaxed">
                {report.summary}
              </div>
            )}

            {/* Pause recommendations */}
            {report.pause_recommendations.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
                  <AlertTriangle className="h-4 w-4 text-yellow-500" />
                  Pause Recommendations ({report.pause_recommendations.length})
                </h4>
                <div className="space-y-2">
                  {report.pause_recommendations.map((rec, i) => (
                    <div key={i} className="flex items-start gap-2 p-3 bg-yellow-50 border border-yellow-100 rounded-lg">
                      <span className="text-xs font-mono text-yellow-700 shrink-0">{rec.creative_id.slice(0, 8)}…</span>
                      <span className="text-xs text-yellow-800">{rec.reason}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Budget shifts */}
            {report.budget_shifts.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-2">Budget Shift Suggestions</h4>
                <div className="space-y-2">
                  {report.budget_shifts.map((shift, i) => (
                    <div key={i} className="p-3 bg-green-50 border border-green-100 rounded-lg text-xs">
                      <div className="flex items-center gap-2 font-medium text-green-800 mb-1">
                        <span className="truncate">{shift.from_campaign}</span>
                        <ArrowRight className="h-3 w-3 shrink-0" />
                        <span className="truncate">{shift.to_campaign}</span>
                        <span className="shrink-0 font-bold">${shift.amount}/day</span>
                      </div>
                      <p className="text-green-700">{shift.reason}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* New copy angles from analysis */}
            {report.new_copy_angles.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-2">Suggested New Creatives to Test</h4>
                <div className="space-y-3">
                  {report.new_copy_angles.map((variant, i) => (
                    <CopyVariantCard key={i} variant={variant} idx={i} copiedIdx={copiedIdx} onCopy={copyVariant} />
                  ))}
                </div>
              </div>
            )}

            {/* Audience suggestions */}
            {report.audience_suggestions.length > 0 && (
              <div>
                <h4 className="text-sm font-semibold text-gray-700 mb-2">Audience Targeting Suggestions</h4>
                <ul className="space-y-1">
                  {report.audience_suggestions.map((sug, i) => (
                    <li key={i} className="text-xs text-gray-600 flex items-start gap-2">
                      <span className="text-[#E8720C] font-bold shrink-0">→</span>
                      {sug}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {!report && !loading && (
          <p className="text-sm text-gray-500 text-center py-6">
            Click "Run Analysis" to get AI-powered recommendations for your campaigns.
          </p>
        )}
      </div>

      {/* Copy Generator Section */}
      <div className="bg-white border rounded-xl p-6">
        <h3 className="font-semibold text-gray-900 mb-1">Ad Copy Generator</h3>
        <p className="text-xs text-gray-500 mb-4">Generate HomeVestors-style copy variants for any seller pain point</p>

        <div className="flex items-center gap-3 mb-4">
          <select
            value={selectedAngle}
            onChange={(e) => setSelectedAngle(e.target.value)}
            className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm"
          >
            {Object.entries(ANGLE_LABELS).map(([val, label]) => (
              <option key={val} value={val}>{label}</option>
            ))}
          </select>
          <button
            onClick={generateVariants}
            disabled={generating}
            className="flex items-center gap-2 px-4 py-2 bg-[#E8720C] text-white text-sm font-medium rounded-lg hover:bg-[#d4660b] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {generating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
            Generate 5 Variants
          </button>
        </div>

        {generatedVariants.length > 0 && (
          <div className="space-y-3">
            {generatedVariants.map((variant, i) => (
              <CopyVariantCard key={i} variant={variant} idx={i + 100} copiedIdx={copiedIdx} onCopy={copyVariant} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function CopyVariantCard({
  variant,
  idx,
  copiedIdx,
  onCopy,
}: {
  variant: AdCopyVariant;
  idx: number;
  copiedIdx: number | null;
  onCopy: (idx: number, variant: AdCopyVariant) => void;
}) {
  return (
    <div className="border border-gray-200 rounded-lg p-4 bg-gray-50">
      <div className="flex items-start justify-between gap-2 mb-2">
        <p className="font-semibold text-gray-900 text-sm leading-snug">{variant.headline}</p>
        <button
          onClick={() => onCopy(idx, variant)}
          className="p-1.5 rounded-lg border border-gray-200 hover:bg-white transition-colors shrink-0"
          title="Copy to clipboard"
        >
          {copiedIdx === idx ? <Check className="h-3.5 w-3.5 text-green-600" /> : <Copy className="h-3.5 w-3.5 text-gray-500" />}
        </button>
      </div>
      <p className="text-xs text-gray-600 leading-relaxed mb-2">{variant.primary_text}</p>
      <div className="flex items-center justify-between">
        <span className="text-xs bg-[#E8720C] text-white px-2 py-0.5 rounded font-medium">{variant.cta}</span>
        {variant.rationale && (
          <span className="text-xs text-gray-400 italic max-w-xs truncate">{variant.rationale}</span>
        )}
      </div>
    </div>
  );
}
