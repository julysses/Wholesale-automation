import { Lock, ArrowRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { SITUATION_OPTIONS, ROUTING_MAP, TWILIO_SEQUENCES } from '@/lib/fb-ads/battlePlanRules';
import { BattlePlanCallout } from './Step1CampaignSettings';

interface Step5State {
  include_mortgage_balance: boolean;
  include_rented: boolean;
  include_best_time: boolean;
  confirmation_message: string;
}

interface Props {
  state: Step5State;
  onChange: (updates: Partial<Step5State>) => void;
}

const REQUIRED_FIELDS = [
  { num: 1, name: 'Property Address', type: 'Text — Free entry', locked: true },
  { num: 2, name: 'Property Condition', type: 'Multiple choice: Good / Fair / Needs Work / Major Repairs', locked: true },
  { num: 3, name: 'Situation', type: 'Multi-select: ' + SITUATION_OPTIONS.join(' / '), locked: true },
  { num: 4, name: 'Timeline', type: 'Multiple choice: ASAP / 1–3 Months / Just Exploring', locked: true },
  { num: 5, name: 'Contact Preference', type: 'Multiple choice: Call / Text', locked: true },
];

const OPTIONAL_FIELDS = [
  { key: 'include_mortgage_balance', label: 'Mortgage balance (Yes/No)' },
  { key: 'include_rented', label: 'Is property currently rented? (Yes/No)' },
  { key: 'include_best_time', label: 'Best time to call' },
] as const;

const SEGMENT_COLORS: Record<string, string> = {
  'HOT-URGENT':      'bg-red-100 text-red-700',
  'HOT-ESTATE':      'bg-red-100 text-red-700',
  'HOT-LEGAL':       'bg-red-100 text-red-700',
  'HOT-TAX':         'bg-red-100 text-red-700',
  'WARM-LANDLORD':   'bg-orange-100 text-orange-700',
  'WARM-RELOCATION': 'bg-orange-100 text-orange-700',
  'COLD-NURTURE':    'bg-gray-100 text-gray-600',
};

export function Step5LeadFormBuilder({ state, onChange }: Props) {
  return (
    <div className="space-y-6">
      <BattlePlanCallout>
        Meta Instant Lead Form fields are locked to battle-plan requirements. The Situation field drives automatic routing to the correct Twilio follow-up sequence.
      </BattlePlanCallout>

      {/* Required Fields */}
      <div>
        <h3 className="text-sm font-bold text-gray-800 mb-3">Required Fields (Locked)</h3>
        <div className="space-y-2">
          {REQUIRED_FIELDS.map(field => (
            <div key={field.num} className="flex items-start gap-3 p-3 bg-gray-50 border border-gray-200 rounded-lg">
              <span className="h-6 w-6 bg-[#0A1628] text-white text-xs font-bold rounded-full flex items-center justify-center shrink-0">
                {field.num}
              </span>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-900">{field.name}</span>
                  <Lock className="h-3.5 w-3.5 text-gray-400" />
                </div>
                <p className="text-xs text-gray-500 mt-0.5">{field.type}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Optional Fields */}
      <div>
        <h3 className="text-sm font-bold text-gray-800 mb-3">Optional Fields</h3>
        <div className="space-y-2">
          {OPTIONAL_FIELDS.map(({ key, label }) => (
            <label key={key} className="flex items-center gap-3 p-3 border border-gray-200 rounded-lg cursor-pointer hover:bg-gray-50 transition-colors">
              <input
                type="checkbox"
                checked={state[key]}
                onChange={(e) => onChange({ [key]: e.target.checked })}
                className="h-4 w-4 rounded accent-[#0A1628]"
              />
              <span className="text-sm text-gray-700">{label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* Routing Map */}
      <div>
        <h3 className="text-sm font-bold text-gray-800 mb-3">WholesaleOS Routing Map</h3>
        <p className="text-xs text-gray-500 mb-3">
          How each Situation tag routes to your pipeline and Twilio follow-up sequence.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs border-collapse">
            <thead>
              <tr className="bg-[#0A1628] text-white">
                <th className="px-3 py-2 text-left font-semibold rounded-tl-lg">Situation Tag</th>
                <th className="px-3 py-2 text-left font-semibold">WholesaleOS Segment</th>
                <th className="px-3 py-2 text-left font-semibold rounded-tr-lg">Twilio Sequence</th>
              </tr>
            </thead>
            <tbody>
              {ROUTING_MAP.map((row, i) => (
                <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                  <td className="px-3 py-2 font-medium text-gray-800">{row.situations}</td>
                  <td className="px-3 py-2">
                    <span className={cn('px-2 py-0.5 rounded text-xs font-semibold', SEGMENT_COLORS[row.segment] || 'bg-gray-100 text-gray-600')}>
                      {row.segment}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-gray-600">{row.twilioSequence}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Confirmation message preview */}
      <div>
        <h3 className="text-sm font-bold text-gray-800 mb-2">Thank You Message (sent after submission)</h3>
        <textarea
          rows={2}
          value={state.confirmation_message}
          onChange={(e) => onChange({ confirmation_message: e.target.value })}
          placeholder="Hi [name], thanks for reaching out. We received your info on [address]. Someone from our team will call you shortly — or reply here if you prefer to text."
          className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[#0A1628]/20"
        />
        <p className="text-xs text-gray-400 mt-1">Tokens: [name], [address] are replaced dynamically</p>
      </div>
    </div>
  );
}
