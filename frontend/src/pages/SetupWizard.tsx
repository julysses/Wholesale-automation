/**
 * SetupWizard — guided 8-step configuration walkthrough.
 *
 * Steps:
 *   1. Welcome & Overview
 *   2. Core: Anthropic API key
 *   3. Core: Supabase connection
 *   4. Agency Identity
 *   5. Skip Trace: BatchData
 *   6. Dialer: BatchDialer
 *   7. SMS Nurture: Launch Control
 *   8. Email Provider
 *   9. Test & Verify
 *  10. Done!
 *
 * Progress is saved to the setup_checklist table.
 * Any step can be skipped (optional steps marked).
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/lib/supabase';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  CheckCircle, Circle, ChevronRight, ChevronLeft, ExternalLink,
  Zap, Phone, MessageSquare, Mail, Building2, Bot, Database,
  Shield, SkipForward, AlertCircle, RefreshCw
} from 'lucide-react';
import { toast } from 'sonner';

// ── Step definitions ──────────────────────────────────────────────────────────

interface WizardStep {
  id: string;
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  optional?: boolean;
  envKey?: string;             // Used to check if already configured via /api/config
  docsUrl?: string;
  content: React.FC<StepProps>;
}

interface StepProps {
  onNext: () => void;
  onSkip: () => void;
  completedSteps: Set<string>;
}

// ── Individual step content components ───────────────────────────────────────

function WelcomeStep({ onNext }: StepProps) {
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-[#1B3A5C] to-[#2a5580] rounded-2xl p-6 text-white">
        <h3 className="text-xl font-bold mb-2">Welcome to WholesaleOS</h3>
        <p className="text-white/80 text-sm leading-relaxed">
          This wizard will walk you through connecting all the services that power
          your automated wholesale pipeline — from lead intake to closing.
        </p>
      </div>

      <div className="space-y-3">
        {[
          { icon: <Bot className="h-4 w-4" />, label: 'AI scoring + underwriting', color: 'bg-purple-100 text-purple-700' },
          { icon: <Phone className="h-4 w-4" />, label: 'Skip trace + dialer automation', color: 'bg-blue-100 text-blue-700' },
          { icon: <MessageSquare className="h-4 w-4" />, label: 'TCPA-compliant SMS nurture', color: 'bg-green-100 text-green-700' },
          { icon: <Shield className="h-4 w-4" />, label: 'Compliance gate at every step', color: 'bg-orange-100 text-orange-700' },
        ].map(({ icon, label, color }) => (
          <div key={label} className="flex items-center gap-3">
            <div className={cn('p-2 rounded-lg', color)}>{icon}</div>
            <span className="text-sm text-gray-700">{label}</span>
          </div>
        ))}
      </div>

      <p className="text-xs text-gray-400">
        All API keys are stored in your <code className="bg-gray-100 px-1 py-0.5 rounded">.env</code> file
        on your server — never in the browser.
      </p>

      <Button onClick={onNext} className="w-full" size="lg">
        Start Setup <ChevronRight className="h-4 w-4 ml-1" />
      </Button>
    </div>
  );
}

function AnthropicStep({ onNext, onSkip }: StepProps) {
  const [status, setStatus] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle');

  const testConnection = async () => {
    setStatus('testing');
    try {
      const resp = await fetch('/api/ai/qualify-lead', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ property_address: 'Test 123 Main St', city: 'Austin' }),
      });
      setStatus(resp.ok ? 'ok' : 'error');
      if (resp.ok) toast.success('Anthropic connection verified');
      else toast.error('Anthropic API test failed — check your ANTHROPIC_API_KEY');
    } catch {
      setStatus('error');
      toast.error('Could not reach the API');
    }
  };

  return (
    <div className="space-y-5">
      <EnvKeyCard
        keyName="ANTHROPIC_API_KEY"
        label="Anthropic API Key"
        description="Powers all AI agents: lead scoring, offer generation, and outreach drafting."
        example="sk-ant-api03-..."
        docsUrl="https://console.anthropic.com/account/keys"
        docsLabel="Get your key"
      />

      <StatusBar status={status} onTest={testConnection} testLabel="Test AI Connection" />

      <div className="flex gap-3">
        <Button onClick={onNext} className="flex-1" disabled={status === 'testing'}>
          {status === 'ok' ? 'Verified — Next' : 'Next'} <ChevronRight className="h-4 w-4 ml-1" />
        </Button>
      </div>
    </div>
  );
}

function AgencyStep({ onNext }: StepProps) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">
        These values appear in all outreach messages sent on your behalf.
        Set them in your <code className="bg-gray-100 px-1 rounded">.env</code> file:
      </p>

      <div className="bg-gray-50 border border-gray-200 rounded-xl overflow-hidden">
        {[
          { key: 'AGENCY_NAME', example: 'Texas Wholesale Solutions', desc: 'Your company or brand name' },
          { key: 'AGENCY_CONTACT_NAME', example: 'Alex', desc: 'First name used in SMS templates' },
          { key: 'AGENCY_PHONE', example: '+15125550100', desc: 'Call-back number (E.164 format)' },
          { key: 'AGENCY_STATE', example: 'TX', desc: 'Two-letter state code' },
        ].map(({ key, example, desc }, i) => (
          <div key={key} className={cn('px-4 py-3', i > 0 && 'border-t border-gray-200')}>
            <div className="flex items-start justify-between gap-4">
              <div>
                <code className="text-xs font-bold text-[#1B3A5C]">{key}</code>
                <p className="text-xs text-gray-500 mt-0.5">{desc}</p>
              </div>
              <code className="text-xs text-gray-400 shrink-0">{example}</code>
            </div>
          </div>
        ))}
      </div>

      <Button onClick={onNext} className="w-full">
        These look good — Next <ChevronRight className="h-4 w-4 ml-1" />
      </Button>
    </div>
  );
}

function BatchDataStep({ onNext, onSkip }: StepProps) {
  return (
    <div className="space-y-5">
      <FeatureCard
        icon={<Phone className="h-5 w-5" />}
        title="Skip Tracing"
        description="BatchData enriches each lead with mobile phone numbers and emails before scoring. Tier A/B leads need a mobile number to reach the dialer."
      />
      <EnvKeyCard
        keyName="BATCHDATA_API_KEY"
        label="BatchData API Key"
        description="Used for property skip tracing (owner phone + email enrichment)."
        example="bd_live_..."
        docsUrl="https://developer.batchdata.com"
        docsLabel="BatchData developer portal"
      />
      <EnvKeyCard
        keyName="AUTO_SKIP_TRACE"
        label="Auto Skip Trace"
        description="Set to true to automatically skip trace every ingested lead."
        example="true"
        isFlag
      />
      <div className="flex gap-3">
        <Button variant="outline" onClick={onSkip} className="flex-1">
          <SkipForward className="h-4 w-4 mr-1" /> Skip for now
        </Button>
        <Button onClick={onNext} className="flex-1">
          Next <ChevronRight className="h-4 w-4 ml-1" />
        </Button>
      </div>
    </div>
  );
}

function BatchDialerStep({ onNext, onSkip }: StepProps) {
  return (
    <div className="space-y-5">
      <FeatureCard
        icon={<Phone className="h-5 w-5" />}
        title="Outbound Dialer — Tier A & B Leads"
        description="Tier A (score 70+) and B (50–69) leads are pushed to BatchDialer for outbound calling. Call results feed back via webhook to update lead status automatically."
      />
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex gap-2 text-xs text-amber-800">
        <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
        <span>Create your campaign in BatchDialer first, then paste the Campaign ID below.</span>
      </div>
      {[
        { key: 'BATCHDIALER_API_KEY', example: 'bd_...', desc: 'Your BatchDialer API key' },
        { key: 'BATCHDIALER_DEFAULT_CAMPAIGN_ID', example: '12345', desc: 'Campaign ID to push leads into' },
        { key: 'BATCHDIALER_WEBHOOK_SECRET', example: 'whsec_...', desc: 'Set in BatchDialer → Webhooks → call completed' },
        { key: 'AUTO_PUSH_TO_DIALER', example: 'false', desc: 'Set true to auto-push after scoring' },
      ].map(({ key, example, desc }) => (
        <div key={key} className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-3">
          <code className="text-xs font-bold text-[#1B3A5C]">{key}</code>
          <p className="text-xs text-gray-500 mt-0.5">{desc}</p>
          <code className="text-xs text-gray-400">e.g. {example}</code>
        </div>
      ))}
      <WebhookCard path="/webhooks/batchdialer/call" label="Configure in BatchDialer → Webhooks:" />
      <div className="flex gap-3">
        <Button variant="outline" onClick={onSkip} className="flex-1">
          <SkipForward className="h-4 w-4 mr-1" /> Skip for now
        </Button>
        <Button onClick={onNext} className="flex-1">
          Next <ChevronRight className="h-4 w-4 ml-1" />
        </Button>
      </div>
    </div>
  );
}

function LaunchControlStep({ onNext, onSkip }: StepProps) {
  const [mode, setMode] = useState<'zapier_webhook' | 'csv_sync'>('zapier_webhook');
  return (
    <div className="space-y-5">
      <FeatureCard
        icon={<MessageSquare className="h-5 w-5" />}
        title="SMS Nurture — Tier C Leads"
        description="Tier C leads (score 30–49) are enrolled in Launch Control SMS campaigns. Opt-out replies trigger automatic DNC suppression."
      />
      <div className="flex rounded-xl border border-gray-200 overflow-hidden">
        {(['zapier_webhook', 'csv_sync'] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={cn(
              'flex-1 py-2.5 text-sm font-medium transition-colors',
              mode === m ? 'bg-[#1B3A5C] text-white' : 'text-gray-600 hover:bg-gray-50'
            )}
          >
            {m === 'zapier_webhook' ? 'Zapier (recommended)' : 'CSV Queue'}
          </button>
        ))}
      </div>

      {mode === 'zapier_webhook' && (
        <div className="space-y-3">
          <div className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-3">
            <code className="text-xs font-bold text-[#1B3A5C]">LAUNCH_CONTROL_MODE</code>
            <p className="text-xs text-gray-500 mt-0.5">Must be set to: <code>zapier_webhook</code></p>
          </div>
          <div className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-3">
            <code className="text-xs font-bold text-[#1B3A5C]">LAUNCH_CONTROL_ZAPIER_HOOK_URL</code>
            <p className="text-xs text-gray-500 mt-0.5">Zapier trigger URL → your Launch Control Zap</p>
          </div>
          <WebhookCard path="/webhooks/launch_control/reply" label="Configure SMS reply webhook in Zapier:" />
        </div>
      )}

      {mode === 'csv_sync' && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-xs text-blue-800">
          In CSV mode, leads queue locally. Download from{' '}
          <code>/webhooks/launch_control/csv-queue</code> and upload to Launch Control manually.
          Set <code>LAUNCH_CONTROL_MODE=csv_sync</code>.
        </div>
      )}

      <div className="flex gap-3">
        <Button variant="outline" onClick={onSkip} className="flex-1">
          <SkipForward className="h-4 w-4 mr-1" /> Skip for now
        </Button>
        <Button onClick={onNext} className="flex-1">
          Next <ChevronRight className="h-4 w-4 ml-1" />
        </Button>
      </div>
    </div>
  );
}

function EmailStep({ onNext, onSkip }: StepProps) {
  return (
    <div className="space-y-5">
      <FeatureCard
        icon={<Mail className="h-5 w-5" />}
        title="Email Outreach"
        description="Email is the preferred channel (highest trust). Set up SendGrid or Mailgun for compliant email outreach."
      />
      {[
        { key: 'EMAIL_PROVIDER', example: 'sendgrid', desc: 'sendgrid | mailgun | instantly' },
        { key: 'SENDGRID_API_KEY', example: 'SG.xxx...', desc: 'SendGrid API key (if using SendGrid)' },
        { key: 'FROM_EMAIL', example: 'alex@yourdomain.com', desc: 'Verified sender email address' },
      ].map(({ key, example, desc }) => (
        <div key={key} className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-3">
          <code className="text-xs font-bold text-[#1B3A5C]">{key}</code>
          <p className="text-xs text-gray-500 mt-0.5">{desc}</p>
          <code className="text-xs text-gray-400">e.g. {example}</code>
        </div>
      ))}
      <div className="flex gap-3">
        <Button variant="outline" onClick={onSkip} className="flex-1">
          <SkipForward className="h-4 w-4 mr-1" /> Skip for now
        </Button>
        <Button onClick={onNext} className="flex-1">
          Next <ChevronRight className="h-4 w-4 ml-1" />
        </Button>
      </div>
    </div>
  );
}

function TestStep({ onNext }: StepProps) {
  const [results, setResults] = useState<Record<string, 'idle' | 'ok' | 'error'>>({
    ai: 'idle', supabase: 'idle', health: 'idle',
  });
  const [running, setRunning] = useState(false);

  const runTests = async () => {
    setRunning(true);
    const next = { ...results };

    // Health check
    try {
      const r = await fetch('/api/health');
      next.health = r.ok ? 'ok' : 'error';
    } catch { next.health = 'error'; }

    // Supabase
    try {
      const { error } = await supabase.from('leads').select('id').limit(1);
      next.supabase = error ? 'error' : 'ok';
    } catch { next.supabase = 'error'; }

    // AI
    try {
      const r = await fetch('/api/ai/qualify-lead', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ property_address: '123 Main St', city: 'Austin' }),
      });
      next.ai = r.ok ? 'ok' : 'error';
    } catch { next.ai = 'error'; }

    setResults(next);
    setRunning(false);
    const allOk = Object.values(next).every(v => v === 'ok');
    if (allOk) toast.success('All systems verified!');
    else toast.error('Some checks failed — review items in red');
  };

  const allOk = Object.values(results).every(v => v === 'ok');
  const hasErrors = Object.values(results).some(v => v === 'error');

  return (
    <div className="space-y-5">
      <div className="space-y-2">
        {[
          { key: 'health', label: 'API Server health check' },
          { key: 'supabase', label: 'Supabase database connection' },
          { key: 'ai', label: 'Anthropic AI (lead qualifier)' },
        ].map(({ key, label }) => (
          <div key={key} className="flex items-center justify-between bg-gray-50 rounded-xl px-4 py-3 border border-gray-200">
            <span className="text-sm text-gray-700">{label}</span>
            <StatusDot status={results[key as keyof typeof results]} />
          </div>
        ))}
      </div>

      <Button onClick={runTests} loading={running} variant="outline" className="w-full" icon={<RefreshCw className="h-4 w-4" />}>
        {running ? 'Running...' : 'Run Checks'}
      </Button>

      {hasErrors && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-3 text-xs text-red-700">
          Some checks failed. Check your <code>.env</code> file and restart the server, then re-run.
        </div>
      )}

      <Button onClick={onNext} className="w-full" disabled={!allOk && !hasErrors}>
        {allOk ? 'Finish Setup' : 'Continue Anyway'} <ChevronRight className="h-4 w-4 ml-1" />
      </Button>
    </div>
  );
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function EnvKeyCard({
  keyName, label, description, example, docsUrl, docsLabel, isFlag,
}: {
  keyName: string; label: string; description: string; example: string;
  docsUrl?: string; docsLabel?: string; isFlag?: boolean;
}) {
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-xl overflow-hidden">
      <div className="px-4 py-3">
        <div className="flex items-center justify-between mb-1">
          <code className="text-xs font-bold text-[#1B3A5C]">{keyName}</code>
          {docsUrl && (
            <a href={docsUrl} target="_blank" rel="noopener noreferrer"
               className="flex items-center gap-1 text-xs text-[#E8720C] hover:underline">
              {docsLabel} <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
        <p className="text-xs text-gray-600 mb-2">{description}</p>
        <div className="bg-white border border-gray-200 rounded-lg px-3 py-2 font-mono text-xs text-gray-500">
          {isFlag ? (
            <span className="text-green-600">{example}</span>
          ) : (
            <span>{example}</span>
          )}
        </div>
      </div>
    </div>
  );
}

function FeatureCard({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
  return (
    <div className="flex gap-3 bg-blue-50 border border-blue-200 rounded-xl p-4">
      <div className="p-2 bg-blue-100 rounded-lg h-fit text-blue-700">{icon}</div>
      <div>
        <p className="text-sm font-semibold text-blue-900">{title}</p>
        <p className="text-xs text-blue-700 mt-0.5 leading-relaxed">{description}</p>
      </div>
    </div>
  );
}

function WebhookCard({ path, label }: { path: string; label: string }) {
  const base = window.location.origin;
  const full = `${base}${path}`;
  return (
    <div className="bg-gray-800 rounded-xl p-3">
      <p className="text-xs text-gray-400 mb-1.5">{label}</p>
      <div className="flex items-center gap-2">
        <code className="text-xs text-green-400 flex-1 truncate">{full}</code>
        <button
          onClick={() => { navigator.clipboard.writeText(full); toast.success('Copied!'); }}
          className="text-xs text-gray-400 hover:text-white border border-gray-600 rounded px-2 py-0.5 shrink-0"
        >
          Copy
        </button>
      </div>
    </div>
  );
}

function StatusBar({ status, onTest, testLabel }: {
  status: 'idle' | 'testing' | 'ok' | 'error'; onTest: () => void; testLabel: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <Button variant="outline" size="sm" onClick={onTest} loading={status === 'testing'} icon={<RefreshCw className="h-4 w-4" />}>
        {testLabel}
      </Button>
      {status === 'ok' && <span className="text-sm text-green-600 font-medium flex items-center gap-1"><CheckCircle className="h-4 w-4" /> Connected</span>}
      {status === 'error' && <span className="text-sm text-red-600 font-medium flex items-center gap-1"><AlertCircle className="h-4 w-4" /> Failed — check key</span>}
    </div>
  );
}

function StatusDot({ status }: { status: 'idle' | 'ok' | 'error' }) {
  if (status === 'ok')    return <span className="flex items-center gap-1 text-xs text-green-600 font-medium"><CheckCircle className="h-4 w-4" /> OK</span>;
  if (status === 'error') return <span className="flex items-center gap-1 text-xs text-red-600 font-medium"><AlertCircle className="h-4 w-4" /> Failed</span>;
  return <span className="h-2.5 w-2.5 rounded-full bg-gray-300" />;
}

// ── Wizard steps registry ─────────────────────────────────────────────────────

const STEPS: WizardStep[] = [
  { id: 'welcome',       title: 'Welcome',          subtitle: 'Overview of the system',         icon: <Building2 className="h-5 w-5" />,     content: WelcomeStep },
  { id: 'anthropic',     title: 'AI Engine',         subtitle: 'Anthropic API key',              icon: <Bot className="h-5 w-5" />,           content: AnthropicStep },
  { id: 'agency',        title: 'Agency Identity',   subtitle: 'Your name + contact info',       icon: <Building2 className="h-5 w-5" />,     content: AgencyStep },
  { id: 'batchdata',     title: 'Skip Tracing',      subtitle: 'BatchData API key',              icon: <Phone className="h-5 w-5" />,         optional: true, content: BatchDataStep },
  { id: 'batchdialer',   title: 'Dialer',            subtitle: 'BatchDialer + webhook',          icon: <Phone className="h-5 w-5" />,         optional: true, content: BatchDialerStep },
  { id: 'launch_control',title: 'SMS Nurture',       subtitle: 'Launch Control setup',           icon: <MessageSquare className="h-5 w-5" />, optional: true, content: LaunchControlStep },
  { id: 'email',         title: 'Email Provider',    subtitle: 'SendGrid / Mailgun',             icon: <Mail className="h-5 w-5" />,          optional: true, content: EmailStep },
  { id: 'test_complete', title: 'Test & Verify',     subtitle: 'Run connection checks',          icon: <Zap className="h-5 w-5" />,           content: TestStep },
];

// ── Main wizard ───────────────────────────────────────────────────────────────

export function SetupWizard() {
  const navigate = useNavigate();
  const [currentIdx, setCurrentIdx] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set());

  // Load saved progress
  useEffect(() => {
    supabase.from('setup_checklist').select('step, completed, skipped').then(({ data }) => {
      if (!data) return;
      const done = new Set(data.filter(r => r.completed || r.skipped).map(r => r.step));
      setCompletedSteps(done);
      // Jump to the first incomplete step
      const firstIncomplete = STEPS.findIndex(s => !done.has(s.id));
      if (firstIncomplete > 0) setCurrentIdx(firstIncomplete);
    });
  }, []);

  const markStep = async (stepId: string, skipped = false) => {
    const { error } = await supabase.from('setup_checklist').upsert({
      step: stepId,
      completed: !skipped,
      skipped,
      completed_at: new Date().toISOString(),
    }, { onConflict: 'user_id,step' });
    if (!error) {
      setCompletedSteps(prev => new Set([...prev, stepId]));
    }
  };

  const handleNext = async () => {
    await markStep(STEPS[currentIdx].id);
    if (currentIdx < STEPS.length - 1) {
      setCurrentIdx(currentIdx + 1);
    } else {
      toast.success('Setup complete! Welcome to WholesaleOS.');
      navigate('/');
    }
  };

  const handleSkip = async () => {
    await markStep(STEPS[currentIdx].id, true);
    if (currentIdx < STEPS.length - 1) {
      setCurrentIdx(currentIdx + 1);
    }
  };

  const step = STEPS[currentIdx];
  const StepContent = step.content;
  const progress = Math.round((completedSteps.size / STEPS.length) * 100);

  return (
    <div className="min-h-screen bg-[#F2F4F6] flex">
      {/* Sidebar progress */}
      <div className="w-64 bg-[#1B3A5C] p-6 flex flex-col">
        <div className="flex items-center gap-2 mb-8">
          <Building2 className="h-7 w-7 text-[#E8720C]" />
          <span className="text-lg font-bold text-white">Setup Wizard</span>
        </div>

        {/* Progress bar */}
        <div className="mb-6">
          <div className="flex justify-between text-xs text-white/60 mb-1">
            <span>Progress</span>
            <span>{progress}%</span>
          </div>
          <div className="h-1.5 bg-white/20 rounded-full overflow-hidden">
            <div className="h-full bg-[#E8720C] rounded-full transition-all duration-500" style={{ width: `${progress}%` }} />
          </div>
        </div>

        {/* Step list */}
        <nav className="space-y-1 flex-1">
          {STEPS.map((s, i) => {
            const done = completedSteps.has(s.id);
            const active = i === currentIdx;
            return (
              <button
                key={s.id}
                onClick={() => setCurrentIdx(i)}
                className={cn(
                  'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left text-sm transition-colors',
                  active ? 'bg-white/15 text-white' : 'text-white/50 hover:text-white/80 hover:bg-white/5'
                )}
              >
                <span className="shrink-0">
                  {done ? (
                    <CheckCircle className="h-4 w-4 text-green-400" />
                  ) : (
                    <Circle className="h-4 w-4" />
                  )}
                </span>
                <span className="truncate">{s.title}</span>
                {s.optional && !done && (
                  <span className="ml-auto text-xs text-white/30">opt</span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Skip entire wizard */}
        <button
          onClick={() => navigate('/')}
          className="mt-4 text-xs text-white/40 hover:text-white/70 text-center"
        >
          Skip wizard — configure later
        </button>
      </div>

      {/* Main content */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-8">
          {/* Step header */}
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-[#1B3A5C] text-white rounded-xl">{step.icon}</div>
            <div>
              <h2 className="text-xl font-bold text-gray-900">{step.title}</h2>
              <p className="text-sm text-gray-400">{step.subtitle}</p>
            </div>
          </div>

          <div className="flex items-center gap-2 mb-6">
            <span className="text-xs text-gray-400">Step {currentIdx + 1} of {STEPS.length}</span>
            {step.optional && (
              <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Optional</span>
            )}
          </div>

          {/* Step-specific content */}
          <StepContent
            onNext={handleNext}
            onSkip={handleSkip}
            completedSteps={completedSteps}
          />

          {/* Back button */}
          {currentIdx > 0 && (
            <button
              onClick={() => setCurrentIdx(currentIdx - 1)}
              className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 mt-4"
            >
              <ChevronLeft className="h-3.5 w-3.5" /> Back
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
