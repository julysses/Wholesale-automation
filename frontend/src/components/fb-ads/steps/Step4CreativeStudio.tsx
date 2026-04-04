import { useState } from 'react';
import { Upload, AlertTriangle, CheckCircle, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { claudeAdvisor, type CopyReview } from '@/lib/fb-ads/claudeAdvisor';
import { BattlePlanCallout } from './Step1CampaignSettings';

interface Step4State {
  image_url?: string;
  image_file?: File;
  copy_a: string;
  copy_b: string;
  copy_c: string;
  active_segment: string;
}

interface Props {
  state: Step4State;
  onChange: (updates: Partial<Step4State>) => void;
  errors: Record<string, string>;
}

const COPY_LABELS = {
  copy_a: { label: 'Version A', template: 'Problem / Solution' },
  copy_b: { label: 'Version B', template: 'Direct / Punchy' },
  copy_c: { label: 'Version C', template: 'Situation-Specific' },
} as const;

const BRAND_PALETTE = { primary: '#0A1628', text: '#FFFFFF', cta: '#F5A623' };

export function Step4CreativeStudio({ state, onChange, errors }: Props) {
  const [activeTab, setActiveTab] = useState<'image' | 'copy' | 'video'>('image');
  const [copyReviews, setCopyReviews] = useState<Partial<Record<keyof typeof COPY_LABELS, CopyReview>>>({});
  const [reviewing, setReviewing] = useState<string | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    onChange({ image_file: file });
    const url = URL.createObjectURL(file);
    setImagePreview(url);
  };

  const reviewCopy = async (key: keyof typeof COPY_LABELS) => {
    const text = state[key as keyof Step4State] as string;
    if (!text) return;
    setReviewing(key);
    try {
      const review = await claudeAdvisor.reviewCopy(text, state.active_segment || 'pre-foreclosure');
      setCopyReviews(prev => ({ ...prev, [key]: review }));
    } catch {
      // silent fail — show error inline
    } finally {
      setReviewing(null);
    }
  };

  return (
    <div className="space-y-6">
      <BattlePlanCallout>
        Images should use navy/charcoal base with white text and gold CTA. Text overlay must be under 20% of image area.
        Copy must include pain-point reference, local DFW signal, and a clear CTA. No generic openers.
      </BattlePlanCallout>

      {/* Tab switcher */}
      <div className="flex gap-1 border-b border-gray-200">
        {(['image', 'copy', 'video'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={cn(
              'px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px',
              activeTab === tab ? 'border-[#F5A623] text-[#0A1628]' : 'border-transparent text-gray-500 hover:text-gray-700'
            )}
          >
            {tab === 'image' ? 'A — Static Image' : tab === 'copy' ? 'B — Copy Builder' : 'C — Video Specs'}
          </button>
        ))}
      </div>

      {/* Tab A — Static Image */}
      {activeTab === 'image' && (
        <div className="space-y-4">
          <label className="flex flex-col items-center justify-center h-48 border-2 border-dashed border-gray-200 rounded-xl cursor-pointer hover:border-gray-300 bg-gray-50 transition-colors overflow-hidden">
            {imagePreview ? (
              <img src={imagePreview} alt="Preview" className="h-full w-full object-cover" />
            ) : (
              <>
                <Upload className="h-8 w-8 text-gray-400 mb-2" />
                <span className="text-sm text-gray-600">Upload ad image</span>
                <span className="text-xs text-gray-400 mt-1">Min 1200px wide · JPG or PNG</span>
              </>
            )}
            <input type="file" accept=".jpg,.jpeg,.png" className="hidden" onChange={handleImageUpload} />
          </label>

          {/* Brand palette validator */}
          <div>
            <h4 className="text-sm font-semibold text-gray-700 mb-2">Brand Palette Reference</h4>
            <div className="flex gap-3">
              {([
                { color: BRAND_PALETTE.primary, label: 'Primary (Navy)' },
                { color: BRAND_PALETTE.text, label: 'Text (White)', border: true },
                { color: BRAND_PALETTE.cta, label: 'CTA (Gold)' },
              ] as const).map(({ color, label, border }) => (
                <div key={label} className="flex items-center gap-2">
                  <div
                    className={cn('h-8 w-8 rounded-lg', border ? 'border border-gray-300' : '')}
                    style={{ backgroundColor: color }}
                  />
                  <span className="text-xs text-gray-600">{label}<br/><code className="text-gray-400">{color}</code></span>
                </div>
              ))}
            </div>
          </div>

          {/* Checklist */}
          <div className="space-y-2">
            {[
              'Navy/charcoal base color detected',
              'White text on dark background',
              'Gold CTA button element',
              'Text overlay under 20% of image area',
              'No smiling agents or luxury homes',
              'Minimum 1200px width',
            ].map((item, i) => (
              <div key={i} className="flex items-center gap-2 text-sm text-gray-600">
                <div className="h-4 w-4 rounded border border-gray-300 flex items-center justify-center">
                  <span className="text-xs text-gray-400">?</span>
                </div>
                {item}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab B — Copy Builder */}
      {activeTab === 'copy' && (
        <div className="space-y-5">
          {(Object.entries(COPY_LABELS) as [keyof typeof COPY_LABELS, { label: string; template: string }][]).map(([key, { label, template }]) => {
            const review = copyReviews[key];
            return (
              <div key={key} className="border border-gray-200 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-sm font-semibold text-gray-900">{label}</span>
                    <span className="ml-2 text-xs text-gray-400">— {template} template</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => reviewCopy(key)}
                    disabled={reviewing === key || !state[key as keyof Step4State]}
                    className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-[#0A1628] text-white rounded-lg hover:bg-[#0a1628]/90 disabled:opacity-50 transition-colors"
                  >
                    {reviewing === key ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : '✦'}
                    Claude Review
                  </button>
                </div>

                <textarea
                  rows={4}
                  placeholder={`Enter ${label.toLowerCase()} copy…`}
                  value={state[key as keyof Step4State] as string}
                  onChange={(e) => onChange({ [key]: e.target.value })}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[#0A1628]/20"
                />

                {review && <CopyScoreCard review={review} />}
              </div>
            );
          })}
        </div>
      )}

      {/* Tab C — Video Specs */}
      {activeTab === 'video' && (
        <div className="space-y-3">
          <p className="text-sm text-gray-600">Reference checklist for video creative. Production must meet all specifications before launch.</p>
          <div className="space-y-2">
            {[
              { spec: '15–30 seconds duration', detail: 'Shorter videos perform better on mobile feed' },
              { spec: 'Mobile-first aspect ratio (9:16 or 1:1)', detail: 'Vertical/square formats get more screen real estate' },
              { spec: 'No agent or luxury home imagery', detail: 'Battle plan requires relatable, realistic DFW properties' },
              { spec: 'Real DFW neighborhood footage', detail: 'Authenticity drives trust with motivated sellers' },
              { spec: 'CTA in final 5 seconds', detail: '"Get your cash offer" or "Call/text us today"' },
              { spec: 'Open captions / subtitles', detail: '85% of video watched without sound on mobile' },
            ].map(({ spec, detail }) => (
              <div key={spec} className="flex items-start gap-3 p-3 bg-gray-50 border border-gray-100 rounded-lg">
                <div className="h-5 w-5 rounded-full border-2 border-gray-300 mt-0.5 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-gray-800">{spec}</p>
                  <p className="text-xs text-gray-500">{detail}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function CopyScoreCard({ review }: { review: CopyReview }) {
  const checks = [
    { label: 'Pain-point reference', pass: review.pain_point_present },
    { label: 'Local signal (DFW)', pass: review.local_signal },
    { label: 'CTA present', pass: review.cta_present },
    { label: 'No generic opener', pass: !review.generic_detected },
  ];
  const hookColor = review.emotional_hook === 'strong' ? 'text-green-600' : review.emotional_hook === 'moderate' ? 'text-yellow-600' : 'text-red-500';

  return (
    <div className="bg-[#0A1628]/5 border border-[#0A1628]/15 rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-[#0A1628]">Claude Copy Review</span>
        <span className={cn('text-xs font-bold', review.score >= 80 ? 'text-green-600' : review.score >= 60 ? 'text-yellow-600' : 'text-red-500')}>
          {review.score}/100
        </span>
      </div>
      <div className="grid grid-cols-2 gap-1">
        {checks.map(({ label, pass }) => (
          <div key={label} className="flex items-center gap-1.5 text-xs">
            {pass ? <CheckCircle className="h-3.5 w-3.5 text-green-500 shrink-0" /> : <AlertTriangle className="h-3.5 w-3.5 text-red-400 shrink-0" />}
            <span className={pass ? 'text-gray-700' : 'text-red-600'}>{label}</span>
          </div>
        ))}
        <div className="flex items-center gap-1.5 text-xs col-span-2">
          <span className="text-gray-500">Emotional hook:</span>
          <span className={cn('font-medium', hookColor)}>
            {review.emotional_hook === 'strong' ? '✅ Strong' : review.emotional_hook === 'moderate' ? '⚠ Moderate' : '❌ Weak'}
          </span>
        </div>
      </div>
      {review.flags.length > 0 && (
        <div className="space-y-1">
          {review.flags.map((f, i) => (
            <div key={i} className="flex items-start gap-1.5">
              <AlertTriangle className="h-3.5 w-3.5 text-amber-500 shrink-0 mt-0.5" />
              <p className="text-xs text-amber-800">{f}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
