import { apiFetch } from '@/lib/api';
import { useState } from 'react';
import { toast } from 'sonner';
import {
  Megaphone, TrendingUp, DollarSign, Users, Flame, Target, Plus, Loader2, RefreshCw
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend
} from 'recharts';
import { cn } from '@/lib/utils';
import { CampaignCard } from '@/components/lead-gen/CampaignCard';
import { AdCreativeABCard } from '@/components/lead-gen/AdCreativeABCard';
import { LeadFormBuilder } from '@/components/lead-gen/LeadFormBuilder';
import { AdOptimizationPanel } from '@/components/lead-gen/AdOptimizationPanel';
import {
  useAdCampaigns, useUpdateCampaign, useCreateCampaign,
  useAdCreatives, useUpdateCreative, useCreateCreative,
  useLeadFormConfigs, useUpdateFormConfig, useCreateFormConfig,
  useLeadFormSubmissions, useLeadGenKPIs, useInboundLeadsTrend,
} from '@/hooks/useLeadGen';
import { formatCurrency } from '@/lib/utils';

const TABS = ['Overview', 'Campaigns & Ads', 'Lead Forms', 'AI Optimizer'] as const;
type Tab = typeof TABS[number];

const PAIN_POINTS = [
  { value: 'foreclosure', label: 'Foreclosure' },
  { value: 'divorce', label: 'Divorce' },
  { value: 'inherited', label: 'Inherited' },
  { value: 'tired_landlord', label: 'Tired Landlord' },
  { value: 'relocation', label: 'Relocation' },
  { value: 'repairs', label: 'Repairs' },
  { value: 'generic', label: 'Generic' },
];

export function LeadGenEngine() {
  const [tab, setTab] = useState<Tab>('Overview');
  const [selectedCampaignId, setSelectedCampaignId] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [showNewCampaign, setShowNewCampaign] = useState(false);
  const [showNewCreative, setShowNewCreative] = useState(false);
  const [showNewForm, setShowNewForm] = useState(false);
  const [newCampaignName, setNewCampaignName] = useState('');
  const [newCreative, setNewCreative] = useState({ name: '', headline: '', primary_text: '', cta_text: 'Get My Cash Offer', pain_point_angle: 'generic' });
  const [newFormName, setNewFormName] = useState('');
  const [newFormSlug, setNewFormSlug] = useState('');

  const { data: campaigns = [], isLoading: loadingCampaigns } = useAdCampaigns();
  const { data: kpis } = useLeadGenKPIs();
  const { data: trend = [] } = useInboundLeadsTrend(30);
  const { data: creatives = [] } = useAdCreatives(selectedCampaignId || undefined);
  const { data: forms = [] } = useLeadFormConfigs();
  const { data: submissions = [] } = useLeadFormSubmissions();

  const updateCampaign = useUpdateCampaign();
  const createCampaign = useCreateCampaign();
  const updateCreative = useUpdateCreative();
  const createCreative = useCreateCreative();
  const updateForm = useUpdateFormConfig();
  const createForm = useCreateFormConfig();

  const handleSyncFacebook = async (id: string) => {
    setSyncingId(id);
    try {
      await apiFetch(`/api/lead-gen/campaigns/${id}/sync-facebook`, { method: 'POST' });
      updateCampaign.mutate({ id, updates: {} }); // trigger refetch
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Campaign sync failed');
    } finally {
      setSyncingId(null);
    }
  };

  const handleCreateCampaign = async () => {
    if (!newCampaignName.trim()) return;
    await createCampaign.mutateAsync({ name: newCampaignName, status: 'draft', platform: 'facebook' });
    setNewCampaignName('');
    setShowNewCampaign(false);
  };

  const handleCreateCreative = async () => {
    if (!newCreative.name.trim() || !selectedCampaignId) return;
    await createCreative.mutateAsync({ ...newCreative, campaign_id: selectedCampaignId });
    setNewCreative({ name: '', headline: '', primary_text: '', cta_text: 'Get My Cash Offer', pain_point_angle: 'generic' });
    setShowNewCreative(false);
  };

  const handleCreateForm = async () => {
    if (!newFormName.trim() || !newFormSlug.trim()) return;
    await createForm.mutateAsync({ name: newFormName, slug: newFormSlug, active: true, questions: [] });
    setNewFormName('');
    setNewFormSlug('');
    setShowNewForm(false);
  };

  const selectedCampaign = campaigns.find((c) => c.id === selectedCampaignId);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Megaphone className="h-7 w-7 text-[#E8720C]" />
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Lead Engine</h1>
          <p className="text-sm text-gray-500">Facebook Lead Ads · Web Forms · AI Copy Optimizer</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-1 -mb-px">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={cn(
                'px-4 py-2.5 text-sm font-medium border-b-2 transition-colors',
                tab === t
                  ? 'border-[#E8720C] text-[#E8720C]'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              )}
            >
              {t}
            </button>
          ))}
        </nav>
      </div>

      {/* ── OVERVIEW TAB ── */}
      {tab === 'Overview' && (
        <div className="space-y-6">
          {/* KPI Strip */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-4">
            <KPICard icon={<Users className="h-5 w-5" />} label="Leads Today" value={kpis?.leads_today ?? '—'} color="blue" />
            <KPICard icon={<TrendingUp className="h-5 w-5" />} label="This Week" value={kpis?.leads_week ?? '—'} color="green" />
            <KPICard icon={<Flame className="h-5 w-5" />} label="HOT Leads" value={kpis?.hot_leads ?? '—'} color="orange" />
            <KPICard icon={<DollarSign className="h-5 w-5" />} label="Avg CPL" value={kpis ? formatCurrency(kpis.avg_cpl, 0) : '—'} color="purple" />
            <KPICard icon={<Target className="h-5 w-5" />} label="Avg Quality" value={kpis ? `${kpis.avg_lead_quality.toFixed(0)}` : '—'} color="blue" />
            <KPICard icon={<DollarSign className="h-5 w-5" />} label="Total Spend" value={kpis ? formatCurrency(kpis.total_spend, 0) : '—'} color="green" />
            <KPICard icon={<TrendingUp className="h-5 w-5" />} label="Est. Cost/Contract" value={kpis ? formatCurrency(kpis.cost_per_contract_est, 0) : '—'} color="orange" />
          </div>

          {/* Trend Chart */}
          <div className="bg-white border rounded-xl p-5">
            <h3 className="font-semibold text-gray-800 mb-4">Inbound Leads — Last 30 Days</h3>
            {trend.length === 0 ? (
              <div className="h-40 flex items-center justify-center text-gray-400 text-sm">
                No inbound leads yet. Set up your first form or Facebook Lead Ad to start.
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={trend}>
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} tickFormatter={(d) => d.slice(5)} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ fontSize: 12 }}
                    labelFormatter={(l) => `Date: ${l}`}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="total" name="Total" stroke="#1B3A5C" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="facebook" name="Facebook" stroke="#1877F2" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="web_form" name="Web Form" stroke="#E8720C" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Top 5 Campaigns */}
          <div className="bg-white border rounded-xl p-5">
            <h3 className="font-semibold text-gray-800 mb-4">Top Campaigns</h3>
            {campaigns.length === 0 ? (
              <p className="text-sm text-gray-500">No campaigns yet. Create one on the Campaigns & Ads tab.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-xs text-gray-500 border-b">
                      <th className="text-left py-2 pr-4 font-medium">Campaign</th>
                      <th className="text-right py-2 px-3 font-medium">Leads</th>
                      <th className="text-right py-2 px-3 font-medium">Spend</th>
                      <th className="text-right py-2 px-3 font-medium">CPL</th>
                      <th className="text-right py-2 px-3 font-medium">Quality</th>
                      <th className="text-right py-2 pl-3 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {campaigns.slice(0, 5).map((c) => (
                      <tr key={c.id} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="py-2 pr-4 font-medium text-gray-900 max-w-[180px] truncate">{c.name}</td>
                        <td className="py-2 px-3 text-right text-gray-700">{c.leads_count}</td>
                        <td className="py-2 px-3 text-right text-gray-700">{formatCurrency(c.total_spend, 0)}</td>
                        <td className={cn('py-2 px-3 text-right font-medium',
                          c.cpl == null ? 'text-gray-400'
                            : c.cpl <= 50 ? 'text-green-600' : c.cpl <= 80 ? 'text-yellow-600' : 'text-red-600'
                        )}>
                          {c.cpl != null ? formatCurrency(c.cpl, 0) : '—'}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-700">
                          {c.avg_lead_quality_score != null ? c.avg_lead_quality_score.toFixed(0) : '—'}
                        </td>
                        <td className="py-2 pl-3 text-right">
                          <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium',
                            c.status === 'active' ? 'bg-green-100 text-green-700'
                              : c.status === 'paused' ? 'bg-yellow-100 text-yellow-700'
                              : 'bg-gray-100 text-gray-600'
                          )}>
                            {c.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── CAMPAIGNS & ADS TAB ── */}
      {tab === 'Campaigns & Ads' && (
        <div className="space-y-5">
          {/* Campaign list */}
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-gray-800">Campaigns</h2>
            <button
              onClick={() => setShowNewCampaign(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1B3A5C] text-white text-sm rounded-lg hover:bg-[#162f4d] transition-colors"
            >
              <Plus className="h-4 w-4" /> New Campaign
            </button>
          </div>

          {showNewCampaign && (
            <div className="flex items-center gap-3 p-4 bg-gray-50 border rounded-xl">
              <input
                autoFocus
                className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm"
                placeholder="Campaign name (e.g., DFW Foreclosure Q2)"
                value={newCampaignName}
                onChange={(e) => setNewCampaignName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreateCampaign()}
              />
              <button onClick={handleCreateCampaign} className="px-3 py-2 bg-[#1B3A5C] text-white text-sm rounded-lg">
                Create
              </button>
              <button onClick={() => setShowNewCampaign(false)} className="px-3 py-2 border rounded-lg text-sm">
                Cancel
              </button>
            </div>
          )}

          {loadingCampaigns ? (
            <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>
          ) : campaigns.length === 0 ? (
            <div className="text-center py-10 text-gray-500 text-sm">No campaigns yet. Click "New Campaign" to create one.</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {campaigns.map((c) => (
                <CampaignCard
                  key={c.id}
                  campaign={c}
                  selected={selectedCampaignId === c.id}
                  onSelect={setSelectedCampaignId}
                  syncing={syncingId === c.id}
                  onToggleStatus={(id, status) => updateCampaign.mutate({ id, updates: { status: status as 'active' | 'paused' | 'completed' | 'draft' } })}
                  onSyncFacebook={handleSyncFacebook}
                />
              ))}
            </div>
          )}

          {/* Creatives for selected campaign */}
          {selectedCampaignId && (
            <div className="mt-6 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-gray-800">
                  Ad Creatives — {selectedCampaign?.name}
                </h3>
                <button
                  onClick={() => setShowNewCreative(true)}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-[#E8720C] text-white text-sm rounded-lg hover:bg-[#d4660b] transition-colors"
                >
                  <Plus className="h-4 w-4" /> Add Creative
                </button>
              </div>

              {showNewCreative && (
                <div className="p-4 bg-gray-50 border rounded-xl space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <input className="border border-gray-200 rounded-lg px-3 py-2 text-sm" placeholder="Creative name" value={newCreative.name} onChange={(e) => setNewCreative((p) => ({ ...p, name: e.target.value }))} />
                    <select className="border border-gray-200 rounded-lg px-3 py-2 text-sm" value={newCreative.pain_point_angle} onChange={(e) => setNewCreative((p) => ({ ...p, pain_point_angle: e.target.value }))}>
                      {PAIN_POINTS.map((pp) => <option key={pp.value} value={pp.value}>{pp.label}</option>)}
                    </select>
                  </div>
                  <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm" placeholder="Headline (e.g., Stop Foreclosure — Get Cash Fast)" value={newCreative.headline} onChange={(e) => setNewCreative((p) => ({ ...p, headline: e.target.value }))} />
                  <textarea rows={2} className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm resize-none" placeholder="Primary text / body copy" value={newCreative.primary_text} onChange={(e) => setNewCreative((p) => ({ ...p, primary_text: e.target.value }))} />
                  <input className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm" placeholder="CTA (default: Get My Cash Offer)" value={newCreative.cta_text} onChange={(e) => setNewCreative((p) => ({ ...p, cta_text: e.target.value }))} />
                  <div className="flex gap-2">
                    <button onClick={handleCreateCreative} className="px-4 py-2 bg-[#E8720C] text-white text-sm rounded-lg">Add Creative</button>
                    <button onClick={() => setShowNewCreative(false)} className="px-4 py-2 border rounded-lg text-sm">Cancel</button>
                  </div>
                </div>
              )}

              <AdCreativeABCard
                creatives={creatives}
                onToggleStatus={(id, status) => updateCreative.mutate({ id, updates: { status: status as 'active' | 'paused' | 'winner' | 'archived' } })}
                onSetWinner={(id) => {
                  // Clear existing winner first, then set new one
                  creatives.forEach((c) => {
                    if (c.is_winner && c.id !== id) updateCreative.mutate({ id: c.id, updates: { is_winner: false } });
                  });
                  updateCreative.mutate({ id, updates: { is_winner: true, status: 'winner' } });
                }}
              />
            </div>
          )}

          {!selectedCampaignId && campaigns.length > 0 && (
            <p className="text-sm text-gray-500 text-center py-4">
              Click a campaign card to view and manage its ad creatives.
            </p>
          )}
        </div>
      )}

      {/* ── LEAD FORMS TAB ── */}
      {tab === 'Lead Forms' && (
        <div className="space-y-5">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-gray-800">Qualification Forms</h2>
            <button
              onClick={() => setShowNewForm(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-[#1B3A5C] text-white text-sm rounded-lg hover:bg-[#162f4d] transition-colors"
            >
              <Plus className="h-4 w-4" /> New Form
            </button>
          </div>

          {showNewForm && (
            <div className="flex items-center gap-3 p-4 bg-gray-50 border rounded-xl flex-wrap">
              <input
                className="flex-1 min-w-40 border border-gray-200 rounded-lg px-3 py-2 text-sm"
                placeholder="Form name (e.g., Houston Motivated Sellers)"
                value={newFormName}
                onChange={(e) => {
                  setNewFormName(e.target.value);
                  setNewFormSlug(e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''));
                }}
              />
              <input
                className="flex-1 min-w-40 border border-gray-200 rounded-lg px-3 py-2 text-sm"
                placeholder="slug (url path)"
                value={newFormSlug}
                onChange={(e) => setNewFormSlug(e.target.value)}
              />
              <button onClick={handleCreateForm} className="px-3 py-2 bg-[#1B3A5C] text-white text-sm rounded-lg">Create</button>
              <button onClick={() => setShowNewForm(false)} className="px-3 py-2 border rounded-lg text-sm">Cancel</button>
            </div>
          )}

          {forms.length === 0 ? (
            <div className="text-center py-10 text-gray-500 text-sm">No forms yet. A default DFW form is available after running migration 009.</div>
          ) : (
            <div className="space-y-4">
              {forms.map((form) => (
                <div key={form.id} className="bg-white border rounded-xl p-5">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="font-semibold text-gray-900">{form.name}</h3>
                      <p className="text-xs text-gray-500 mt-0.5">/form/{form.slug}</p>
                    </div>
                    <span className={cn('text-xs px-2 py-0.5 rounded-full font-medium', form.active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500')}>
                      {form.active ? 'Active' : 'Inactive'}
                    </span>
                  </div>
                  <LeadFormBuilder
                    form={form}
                    onUpdate={(id, updates) => updateForm.mutate({ id, updates })}
                  />
                </div>
              ))}
            </div>
          )}

          {/* Submissions log */}
          {submissions.length > 0 && (
            <div className="bg-white border rounded-xl p-5 mt-4">
              <h3 className="font-semibold text-gray-800 mb-4">Recent Submissions</h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-gray-500 border-b">
                      <th className="text-left py-2 pr-3 font-medium">Date</th>
                      <th className="text-left py-2 px-3 font-medium">Address</th>
                      <th className="text-left py-2 px-3 font-medium">Motivation</th>
                      <th className="text-left py-2 px-3 font-medium">Timeline</th>
                      <th className="text-left py-2 px-3 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {submissions.slice(0, 20).map((sub) => (
                      <tr key={sub.id} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="py-1.5 pr-3 text-gray-500 whitespace-nowrap">
                          {new Date(sub.created_at).toLocaleDateString()}
                        </td>
                        <td className="py-1.5 px-3 max-w-[180px] truncate text-gray-700">
                          {(sub.raw_answers as any)?.property_address || '—'}
                        </td>
                        <td className="py-1.5 px-3 text-gray-600">{sub.computed_motivation_tag || '—'}</td>
                        <td className="py-1.5 px-3 text-gray-600">{sub.computed_timeline || '—'}</td>
                        <td className="py-1.5 px-3">
                          <span className={cn('px-1.5 py-0.5 rounded text-xs font-medium',
                            sub.processing_status === 'processed' ? 'bg-green-100 text-green-700'
                              : sub.processing_status === 'failed' ? 'bg-red-100 text-red-700'
                              : 'bg-yellow-100 text-yellow-700'
                          )}>
                            {sub.processing_status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── AI OPTIMIZER TAB ── */}
      {tab === 'AI Optimizer' && (
        <AdOptimizationPanel />
      )}
    </div>
  );
}

function KPICard({
  icon, label, value, color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  color: 'blue' | 'orange' | 'green' | 'purple';
}) {
  const colorMap = {
    blue: 'bg-blue-100 text-blue-600',
    orange: 'bg-orange-100 text-[#E8720C]',
    green: 'bg-green-100 text-green-600',
    purple: 'bg-purple-100 text-purple-600',
  };
  return (
    <div className="bg-white border rounded-xl p-4 shadow-sm">
      <div className={cn('inline-flex p-2 rounded-lg mb-2', colorMap[color])}>
        {icon}
      </div>
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-xl font-bold text-gray-900">{value}</p>
    </div>
  );
}
