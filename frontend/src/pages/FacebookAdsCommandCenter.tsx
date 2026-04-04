import { useState } from 'react';
import { Megaphone, LayoutDashboard, Settings, Users, BarChart3, BookOpen } from 'lucide-react';
import { cn } from '@/lib/utils';
import { CampaignWizard } from '@/components/fb-ads/CampaignWizard';
import { ActiveCampaignsDashboard } from '@/components/fb-ads/ActiveCampaignsDashboard';
import { LeadIntakeRouter } from '@/components/fb-ads/LeadIntakeRouter';
import { PerformanceTracker } from '@/components/fb-ads/PerformanceTracker';
import { BattlePlanLibrary } from '@/components/fb-ads/BattlePlanLibrary';

type View =
  | 'dashboard'
  | 'wizard-new'
  | 'wizard-edit'
  | 'leads'
  | 'performance'
  | 'library';

const NAV_ITEMS = [
  { id: 'dashboard',    label: 'Campaigns',       icon: LayoutDashboard },
  { id: 'leads',        label: 'Lead Router',      icon: Users },
  { id: 'performance',  label: 'Performance',      icon: BarChart3 },
  { id: 'library',      label: 'Battle Plan',      icon: BookOpen },
] as const;

export function FacebookAdsCommandCenter() {
  const [view, setView] = useState<View>('dashboard');
  const [editingCampaignId, setEditingCampaignId] = useState<string | undefined>();

  const handleNewCampaign = () => setView('wizard-new');
  const handleEditCampaign = (id: string) => {
    setEditingCampaignId(id);
    setView('wizard-edit');
  };
  const handleWizardComplete = (_id: string) => {
    setView('dashboard');
    setEditingCampaignId(undefined);
  };
  const handleWizardCancel = () => {
    setView('dashboard');
    setEditingCampaignId(undefined);
  };

  const isWizard = view === 'wizard-new' || view === 'wizard-edit';

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 bg-[#0A1628] rounded-xl flex items-center justify-center">
          <Megaphone className="h-5 w-5 text-[#F5A623]" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">FB Ads Command Center</h1>
          <p className="text-sm text-gray-500">DFW Motivated Seller Acquisition · Battle Plan Enforced</p>
        </div>
      </div>

      {/* Tabs (hide during wizard) */}
      {!isWizard && (
        <div className="border-b border-gray-200">
          <nav className="flex gap-1 -mb-px">
            {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setView(id as View)}
                className={cn(
                  'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors',
                  view === id
                    ? 'border-[#F5A623] text-[#0A1628]'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                )}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </nav>
        </div>
      )}

      {/* Content */}
      {view === 'dashboard' && (
        <ActiveCampaignsDashboard
          onNewCampaign={handleNewCampaign}
          onEditCampaign={handleEditCampaign}
        />
      )}

      {isWizard && (
        <div>
          <div className="flex items-center gap-2 mb-6">
            <button
              onClick={handleWizardCancel}
              className="text-sm text-gray-500 hover:text-gray-700 transition-colors"
            >
              ← Back to Campaigns
            </button>
            <span className="text-gray-300">·</span>
            <span className="text-sm font-medium text-gray-700">
              {view === 'wizard-new' ? 'New Campaign Setup Wizard' : 'Edit Campaign'}
            </span>
          </div>
          <CampaignWizard
            campaignId={view === 'wizard-edit' ? editingCampaignId : undefined}
            onComplete={handleWizardComplete}
            onCancel={handleWizardCancel}
          />
        </div>
      )}

      {view === 'leads' && <LeadIntakeRouter />}
      {view === 'performance' && <PerformanceTracker />}
      {view === 'library' && <BattlePlanLibrary />}
    </div>
  );
}
