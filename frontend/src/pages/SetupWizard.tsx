/**
 * SetupWizard — guided configuration walkthrough.
 *
 * API keys entered here are saved to the `app_settings` Supabase table.
 * Vercel environment variables remain the primary source; Supabase fills
 * in any blanks on each backend cold start.
 */
import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { supabase } from '@/lib/supabase';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  CheckCircle, Circle, ChevronRight, ChevronLeft, ExternalLink,
  Zap, Phone, MessageSquare, Mail, Building2, Bot, Database,
  Shield, SkipForward, AlertCircle, RefreshCw, Eye, EyeOff,
} from 'lucide-react';
import { toast } from 'sonner';

// ── Supabase settings helpers ─────────────────────────────────────────────────

async function fetchAppSettings(): Promise<Record<string, string>> {
  const { data } = await supabase.from('app_settings').select('key,value');
  if (!data) return {};
  return Object.fromEntries(data.map((r: any) => [r.key, r.value]));
}

async function saveAppSettings(values: Record<string, string>): Promise<void> {
  const rows = Object.entries(values)
    .filter(([, v]) => v.trim() !== '')
    .map(([key, value]) => ({ key, value }));
  if (rows.length === 0) return;
  const { error } = await supabase.from('app_settings').upsert(rows, { onConflict: 'key' });
  if (error) throw error;
}

// ── Shared UI sub-components ──────────────────────────────────────────────────

function SecretInput({
  value, onChange, placeholder,
}: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="relative">
      <input
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={e => onChange(e.target.value)}
        onPaste={e => {
          e.stopPropagation();
          const text = e.clipboardData.getData('text');
          onChange(text);
          e.preventDefault();
        }}
        placeholder={placeholder}
        autoComplete="off"
        spellCheck={false}
        className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 pr-9 font-mono text-xs text-gray-800 focus:outline-none focus:ring-2 focus:ring-[#1B3A5C]/20 focus:border-[#1B3A5C] placeholder:text-gray-400"
      />
      <button
        type="button"
        onClick={() => setVisible(v => !v)}
        className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
        tabIndex={-1}
      >
        {visible ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}

function TextInput({
  value, onChange, placeholder,
}: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <input
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
      onPaste={e => e.stopPropagation()}
      placeholder={placeholder}
      autoComplete="off"
      className="w-full bg-white border border-gray-200 rounded-lg px-3 py-2 font-mono text-xs text-gray-800 focus:outline-none focus:ring-2 focus:ring-[#1B3A5C]/20 focus:border-[#1B3A5C] placeholder:text-gray-400"
    />
  );
}

function KeyField({
  envKey, label, description, example, docsUrl, docsLabel, isSecret = true, isFlag,
  value, onChange, wasSaved,
}: {
  envKey: string; label: string; description: string; example: string;
  docsUrl?: string; docsLabel?: string; isSecret?: boolean; isFlag?: boolean;
  value: string; onChange: (v: string) => void; wasSaved?: boolean;
}) {
  const savedFromDb = wasSaved && value !== '';
  return (
    <div className="bg-gray-50 border border-gray-200 rounded-xl overflow-hidden">
      <div className="px-4 py-3 space-y-2">
        <div className="flex items-center justify-between">
          <code className="text-xs font-bold text-[#1B3A5C]">{envKey}</code>
          {docsUrl && (
            <a href={docsUrl} target="_blank" rel="noopener noreferrer"
               className="flex items-center gap-1 text-xs text-[#E8720C] hover:underline">
              {docsLabel ?? 'Docs'} <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
        <p className="text-xs text-gray-600">{description}</p>
        {isFlag ? (
          <TextInput value={value} onChange={onChange} placeholder={`e.g. ${example}`} />
        ) : isSecret ? (
          <SecretInput value={value} onChange={onChange} placeholder={`e.g. ${example}`} />
        ) : (
          <TextInput value={value} onChange={onChange} placeholder={`e.g. ${example}`} />
        )}
        {value && (
          <p className="text-xs text-green-600 flex items-center gap-1">
            <CheckCircle className="h-3 w-3" /> {savedFromDb ? 'Previously saved' : 'Entered'}
          </p>
        )}
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
  const full = `${window.location.origin}${path}`;
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

// ── Step interfaces ───────────────────────────────────────────────────────────

interface StepProps {
  onNext: (values?: Record<string, string>) => void;
  onSkip: () => void;
  saved: Record<string, string>;
  onAutoComplete?: () => Promise<void>;
}

// ── Step components ───────────────────────────────────────────────────────────

function WelcomeStep({ onNext, onSkip }: StepProps) {
  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-br from-[#1B3A5C] to-[#2a5580] rounded-2xl p-6 text-white">
        <h3 className="text-xl font-bold mb-2">Welcome to WholesaleOS</h3>
        <p className="text-white/80 text-sm leading-relaxed">
          This wizard connects all the services that power your automated wholesale
          pipeline — from lead intake to closing.
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
        Keys entered here are saved to your Supabase settings and supplement any
        Vercel environment variables you've already configured.
      </p>
      <Button onClick={() => onNext()} className="w-full" size="lg">
        Start Setup <ChevronRight className="h-4 w-4 ml-1" />
      </Button>
      <button onClick={onSkip} className="text-xs text-gray-400 hover:text-gray-600 w-full text-center">
        Skip for now
      </button>
    </div>
  );
}

function AnthropicStep({ onNext, onSkip, saved, onAutoComplete }: StepProps) {
  const [key, setKey] = useState(saved['anthropic_api_key'] ?? '');
  const [status, setStatus] = useState<'idle' | 'testing' | 'ok' | 'error'>('idle');

  const testConnection = async () => {
    if (!key.trim()) {
      toast.error('Enter your API key first');
      return;
    }
    setStatus('testing');
    try {
      await saveAppSettings({ anthropic_api_key: key });
      const resp = await fetch('/api/ai/test');
      if (resp.ok) {
        setStatus('ok');
        toast.success('Anthropic connection verified');
        await onAutoComplete?.();
      } else {
        setStatus('error');
        toast.error('Anthropic API test failed — check your key');
      }
    } catch {
      setStatus('error');
      toast.error('Could not reach the API');
    }
  };

  return (
    <div className="space-y-5">
      <KeyField
        envKey="ANTHROPIC_API_KEY"
        label="Anthropic API Key"
        description="Powers all AI agents: lead scoring, offer generation, and outreach drafting."
        example="sk-ant-api03-..."
        docsUrl="https://console.anthropic.com/account/keys"
        docsLabel="Get key"
        value={key}
        onChange={setKey}
        wasSaved={!!saved['anthropic_api_key']}
      />
      <StatusBar status={status} onTest={testConnection} testLabel="Test AI Connection" />
      <div className="flex gap-3">
        <Button variant="outline" onClick={onSkip} className="flex-1"><SkipForward className="h-4 w-4 mr-1" /> Skip</Button>
        <Button onClick={() => onNext({ anthropic_api_key: key })} className="flex-1" disabled={status === 'testing'}>
          {status === 'ok' ? 'Verified — Next' : 'Save & Next'} <ChevronRight className="h-4 w-4 ml-1" />
        </Button>
      </div>
    </div>
  );
}

function AgencyStep({ onNext, onSkip, saved }: StepProps) {
  const [vals, setVals] = useState({
    agency_name:         saved['agency_name']         ?? '',
    agency_contact_name: saved['agency_contact_name'] ?? '',
    agency_phone:        saved['agency_phone']        ?? '',
    agency_state:        saved['agency_state']        ?? '',
  });
  const set = (k: keyof typeof vals) => (v: string) => setVals(prev => ({ ...prev, [k]: v }));

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">
        These values appear in all outreach messages sent on your behalf.
      </p>
      <KeyField envKey="AGENCY_NAME" label="Agency Name" description="Your company or brand name" example="Texas Wholesale Solutions" isSecret={false} value={vals.agency_name} onChange={set('agency_name')} wasSaved={!!saved['agency_name']} />
      <KeyField envKey="AGENCY_CONTACT_NAME" label="Contact First Name" description="First name used in SMS templates" example="Alex" isSecret={false} value={vals.agency_contact_name} onChange={set('agency_contact_name')} wasSaved={!!saved['agency_contact_name']} />
      <KeyField envKey="AGENCY_PHONE" label="Call-back Phone" description="E.164 format, e.g. +15125550100" example="+15125550100" isSecret={false} value={vals.agency_phone} onChange={set('agency_phone')} wasSaved={!!saved['agency_phone']} />
      <KeyField envKey="AGENCY_STATE" label="State Code" description="Two-letter state, e.g. TX" example="TX" isSecret={false} value={vals.agency_state} onChange={set('agency_state')} wasSaved={!!saved['agency_state']} />
      <div className="flex gap-3">
        <Button variant="outline" onClick={onSkip} className="flex-1"><SkipForward className="h-4 w-4 mr-1" /> Skip</Button>
        <Button onClick={() => onNext(vals)} className="flex-1">
          Save & Next <ChevronRight className="h-4 w-4 ml-1" />
        </Button>
      </div>
    </div>
  );
}

function BatchDataStep({ onNext, onSkip, saved }: StepProps) {
  const [key, setKey] = useState(saved['batchdata_api_key'] ?? '');
  const [autoTrace, setAutoTrace] = useState(saved['auto_skip_trace'] ?? 'true');

  return (
    <div className="space-y-5">
      <FeatureCard
        icon={<Phone className="h-5 w-5" />}
        title="Skip Tracing"
        description="BatchData enriches each lead with mobile phone numbers and emails before scoring. Tier A/B leads need a mobile number to reach the dialer."
      />
      <KeyField envKey="BATCHDATA_API_KEY" label="BatchData API Key" description="Used for property skip tracing (owner phone + email enrichment)." example="bd_live_..." docsUrl="https://developer.batchdata.com" docsLabel="BatchData portal" value={key} onChange={setKey} />
      <KeyField envKey="AUTO_SKIP_TRACE" label="Auto Skip Trace" description="Set to true to automatically skip trace every ingested lead." example="true" isFlag isSecret={false} value={autoTrace} onChange={setAutoTrace} />
      <div className="flex gap-3">
        <Button variant="outline" onClick={onSkip} className="flex-1"><SkipForward className="h-4 w-4 mr-1" /> Skip</Button>
        <Button onClick={() => onNext({ batchdata_api_key: key, auto_skip_trace: autoTrace })} className="flex-1">Save & Next <ChevronRight className="h-4 w-4 ml-1" /></Button>
      </div>
    </div>
  );
}

function BatchDialerStep({ onNext, onSkip, saved }: StepProps) {
  const [vals, setVals] = useState({
    batchdialer_api_key:              saved['batchdialer_api_key']              ?? '',
    batchdialer_default_campaign_id:  saved['batchdialer_default_campaign_id']  ?? '',
    batchdialer_webhook_secret:       saved['batchdialer_webhook_secret']       ?? '',
    auto_push_to_dialer:              saved['auto_push_to_dialer']              ?? 'false',
  });
  const set = (k: keyof typeof vals) => (v: string) => setVals(prev => ({ ...prev, [k]: v }));

  return (
    <div className="space-y-5">
      <FeatureCard icon={<Phone className="h-5 w-5" />} title="Outbound Dialer — Tier A & B Leads" description="Tier A (score 70+) and B (50–69) leads are pushed to BatchDialer for outbound calling." />
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex gap-2 text-xs text-amber-800">
        <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
        <span>Create your campaign in BatchDialer first, then paste the Campaign ID below.</span>
      </div>
      <KeyField envKey="BATCHDIALER_API_KEY" label="BatchDialer API Key" description="Your BatchDialer API key" example="bd_..." value={vals.batchdialer_api_key} onChange={set('batchdialer_api_key')} />
      <KeyField envKey="BATCHDIALER_DEFAULT_CAMPAIGN_ID" label="Default Campaign ID" description="Campaign ID to push leads into" example="12345" isSecret={false} value={vals.batchdialer_default_campaign_id} onChange={set('batchdialer_default_campaign_id')} />
      <KeyField envKey="BATCHDIALER_WEBHOOK_SECRET" label="Webhook Secret" description="Set in BatchDialer → Webhooks → call completed" example="whsec_..." value={vals.batchdialer_webhook_secret} onChange={set('batchdialer_webhook_secret')} />
      <KeyField envKey="AUTO_PUSH_TO_DIALER" label="Auto Push to Dialer" description="Set true to auto-push scored Tier A/B leads" example="false" isFlag isSecret={false} value={vals.auto_push_to_dialer} onChange={set('auto_push_to_dialer')} />
      <WebhookCard path="/webhooks/batchdialer/call" label="Configure in BatchDialer → Webhooks:" />
      <div className="flex gap-3">
        <Button variant="outline" onClick={onSkip} className="flex-1"><SkipForward className="h-4 w-4 mr-1" /> Skip</Button>
        <Button onClick={() => onNext(vals)} className="flex-1">Save & Next <ChevronRight className="h-4 w-4 ml-1" /></Button>
      </div>
    </div>
  );
}

function RetellStep({ onNext, onSkip, saved }: StepProps) {
  const [vals, setVals] = useState({
    retell_api_key:         saved['retell_api_key']         ?? '',
    retell_agent_id:        saved['retell_agent_id']        ?? '',
    retell_from_number:     saved['retell_from_number']     ?? '',
    retell_webhook_secret:  saved['retell_webhook_secret']  ?? '',
  });
  const set = (k: keyof typeof vals) => (v: string) => setVals(prev => ({ ...prev, [k]: v }));

  return (
    <div className="space-y-5">
      <FeatureCard icon={<Bot className="h-5 w-5" />} title="Retell AI — Voice Calling" description="Retell AI handles outbound seller calls, qualifies leads with natural conversation, and fires webhooks when calls complete." />
      <KeyField envKey="RETELL_API_KEY" label="Retell API Key" description="From Retell dashboard → Settings → API Keys" example="key_..." docsUrl="https://app.retellai.com" docsLabel="Dashboard" value={vals.retell_api_key} onChange={set('retell_api_key')} />
      <KeyField envKey="RETELL_AGENT_ID" label="Agent ID" description="The ID of your Retell voice agent" example="agent_..." isSecret={false} value={vals.retell_agent_id} onChange={set('retell_agent_id')} />
      <KeyField envKey="RETELL_FROM_NUMBER" label="From Number" description="E.164 phone number registered in Retell" example="+15125550100" isSecret={false} value={vals.retell_from_number} onChange={set('retell_from_number')} />
      <KeyField envKey="RETELL_WEBHOOK_SECRET" label="Webhook Secret" description="Set in Retell → Webhooks (verifies inbound events)" example="whsec_..." value={vals.retell_webhook_secret} onChange={set('retell_webhook_secret')} />
      <WebhookCard path="/webhooks/retell/call_ended" label="Retell webhook URL:" />
      <div className="flex gap-3">
        <Button variant="outline" onClick={onSkip} className="flex-1"><SkipForward className="h-4 w-4 mr-1" /> Skip</Button>
        <Button onClick={() => onNext(vals)} className="flex-1">Save & Next <ChevronRight className="h-4 w-4 ml-1" /></Button>
      </div>
    </div>
  );
}

function LaunchControlStep({ onNext, onSkip, saved }: StepProps) {
  const [mode, setMode] = useState<'zapier_webhook' | 'csv_sync'>('zapier_webhook');
  const [hookUrl, setHookUrl] = useState(saved['launch_control_zapier_hook_url'] ?? '');

  return (
    <div className="space-y-5">
      <FeatureCard icon={<MessageSquare className="h-5 w-5" />} title="SMS Nurture — Tier C Leads" description="Tier C leads (score 30–49) are enrolled in Launch Control SMS campaigns. Opt-out replies trigger automatic DNC suppression." />
      <div className="flex rounded-xl border border-gray-200 overflow-hidden">
        {(['zapier_webhook', 'csv_sync'] as const).map(m => (
          <button key={m} onClick={() => setMode(m)} className={cn('flex-1 py-2.5 text-sm font-medium transition-colors', mode === m ? 'bg-[#1B3A5C] text-white' : 'text-gray-600 hover:bg-gray-50')}>
            {m === 'zapier_webhook' ? 'Zapier (recommended)' : 'CSV Queue'}
          </button>
        ))}
      </div>
      {mode === 'zapier_webhook' && (
        <KeyField envKey="LAUNCH_CONTROL_ZAPIER_HOOK_URL" label="Zapier Hook URL" description="Zapier trigger URL → your Launch Control Zap" example="https://hooks.zapier.com/..." isSecret={false} value={hookUrl} onChange={setHookUrl} />
      )}
      {mode === 'csv_sync' && (
        <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 text-xs text-blue-800">
          In CSV mode, leads queue locally. Download from <code>/webhooks/launch_control/csv-queue</code> and upload to Launch Control manually.
        </div>
      )}
      <WebhookCard path="/webhooks/launch_control/reply" label="SMS reply webhook (set in Zapier):" />
      <div className="flex gap-3">
        <Button variant="outline" onClick={onSkip} className="flex-1"><SkipForward className="h-4 w-4 mr-1" /> Skip</Button>
        <Button onClick={() => onNext({ launch_control_mode: mode, launch_control_zapier_hook_url: hookUrl })} className="flex-1">Save & Next <ChevronRight className="h-4 w-4 ml-1" /></Button>
      </div>
    </div>
  );
}

function EmailStep({ onNext, onSkip, saved }: StepProps) {
  const [vals, setVals] = useState({
    email_provider:   saved['email_provider']   ?? 'sendgrid',
    sendgrid_api_key: saved['sendgrid_api_key'] ?? '',
    from_email:       saved['from_email']       ?? '',
  });
  const set = (k: keyof typeof vals) => (v: string) => setVals(prev => ({ ...prev, [k]: v }));

  return (
    <div className="space-y-5">
      <FeatureCard icon={<Mail className="h-5 w-5" />} title="Email Outreach" description="Email is the preferred channel (highest trust). Set up SendGrid or Mailgun for compliant email outreach." />
      <KeyField envKey="EMAIL_PROVIDER" label="Email Provider" description="sendgrid | mailgun | instantly" example="sendgrid" isSecret={false} value={vals.email_provider} onChange={set('email_provider')} />
      <KeyField envKey="SENDGRID_API_KEY" label="SendGrid API Key" description="SendGrid API key (if using SendGrid)" example="SG.xxx..." value={vals.sendgrid_api_key} onChange={set('sendgrid_api_key')} />
      <KeyField envKey="FROM_EMAIL" label="From Email" description="Verified sender email address" example="alex@yourdomain.com" isSecret={false} value={vals.from_email} onChange={set('from_email')} />
      <div className="flex gap-3">
        <Button variant="outline" onClick={onSkip} className="flex-1"><SkipForward className="h-4 w-4 mr-1" /> Skip</Button>
        <Button onClick={() => onNext(vals)} className="flex-1">Save & Next <ChevronRight className="h-4 w-4 ml-1" /></Button>
      </div>
    </div>
  );
}

function TestStep({ onNext }: StepProps) {
  const [results, setResults] = useState<Record<string, 'idle' | 'ok' | 'error'>>({
    health: 'idle', supabase: 'idle', ai: 'idle',
  });
  const [running, setRunning] = useState(false);

  const runTests = async () => {
    setRunning(true);
    const next = { ...results };
    try { const r = await fetch('/api/health'); next.health = r.ok ? 'ok' : 'error'; } catch { next.health = 'error'; }
    try { const { error } = await supabase.from('leads').select('id').limit(1); next.supabase = error ? 'error' : 'ok'; } catch { next.supabase = 'error'; }
    try {
      const r = await fetch('/api/ai/qualify-lead', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ property_address: '123 Main St', city: 'Austin' }) });
      next.ai = r.ok ? 'ok' : 'error';
    } catch { next.ai = 'error'; }
    setResults(next);
    setRunning(false);
    if (Object.values(next).every(v => v === 'ok')) toast.success('All systems verified!');
    else toast.error('Some checks failed — see items in red');
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
          Some checks failed. Verify your keys above and re-run. Keys entered in the wizard are saved to Supabase and loaded on the next backend cold start.
        </div>
      )}
      <Button onClick={() => onNext()} className="w-full" disabled={!allOk && !hasErrors}>
        {allOk ? 'Finish Setup' : 'Continue Anyway'} <ChevronRight className="h-4 w-4 ml-1" />
      </Button>
    </div>
  );
}

// ── Step registry ─────────────────────────────────────────────────────────────

interface WizardStep {
  id: string;
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  optional?: boolean;
  content: React.FC<StepProps>;
}

const STEPS: WizardStep[] = [
  { id: 'welcome',        title: 'Welcome',          subtitle: 'Overview of the system',     icon: <Building2 className="h-5 w-5" />,     content: WelcomeStep },
  { id: 'anthropic',      title: 'AI Engine',         subtitle: 'Anthropic API key',          icon: <Bot className="h-5 w-5" />,           content: AnthropicStep },
  { id: 'agency',         title: 'Agency Identity',   subtitle: 'Your name + contact info',   icon: <Building2 className="h-5 w-5" />,     content: AgencyStep },
  { id: 'batchdata',      title: 'Skip Tracing',      subtitle: 'BatchData API key',          icon: <Phone className="h-5 w-5" />,         optional: true, content: BatchDataStep },
  { id: 'batchdialer',    title: 'Dialer',            subtitle: 'BatchDialer + webhook',      icon: <Phone className="h-5 w-5" />,         optional: true, content: BatchDialerStep },
  { id: 'retell',         title: 'AI Calling',        subtitle: 'Retell AI voice agent',      icon: <Bot className="h-5 w-5" />,           optional: true, content: RetellStep },
  { id: 'launch_control', title: 'SMS Nurture',       subtitle: 'Launch Control setup',       icon: <MessageSquare className="h-5 w-5" />, optional: true, content: LaunchControlStep },
  { id: 'email',          title: 'Email Provider',    subtitle: 'SendGrid / Mailgun',         icon: <Mail className="h-5 w-5" />,          optional: true, content: EmailStep },
  { id: 'test_complete',  title: 'Test & Verify',     subtitle: 'Run connection checks',      icon: <Zap className="h-5 w-5" />,           content: TestStep },
];

// ── Main wizard ───────────────────────────────────────────────────────────────

export function SetupWizard() {
  const navigate = useNavigate();
  const [currentIdx, setCurrentIdx] = useState(0);
  const [completedSteps, setCompletedSteps] = useState<Set<string>>(new Set());
  const [savedSettings, setSavedSettings] = useState<Record<string, string>>({});
  const [settingsLoaded, setSettingsLoaded] = useState(false);

  useEffect(() => {
    Promise.all([
      supabase.from('setup_checklist').select('step,completed,skipped'),
      fetchAppSettings(),
    ]).then(([checklistRes, appSettings]) => {
      const data = checklistRes.data ?? [];
      const done = new Set(data.filter((r: any) => r.completed || r.skipped).map((r: any) => r.step as string));
      setCompletedSteps(done);
      setSavedSettings(appSettings);
      setSettingsLoaded(true);
      const firstIncomplete = STEPS.findIndex(s => !done.has(s.id));
      if (firstIncomplete > 0) setCurrentIdx(firstIncomplete);
    });
  }, []);

  const markStep = async (stepId: string, skipped = false) => {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) return;
    await supabase.from('setup_checklist').upsert({
      user_id: user.id,
      step: stepId,
      completed: !skipped,
      skipped,
      completed_at: new Date().toISOString(),
    }, { onConflict: 'user_id,step' });
    setCompletedSteps(prev => new Set([...prev, stepId]));
  };

  const handleNext = useCallback(async (values?: Record<string, string>) => {
    if (values && Object.keys(values).length > 0) {
      try {
        await saveAppSettings(values);
        setSavedSettings(prev => ({ ...prev, ...values }));
      } catch (err) {
        toast.error('Failed to save settings — check Supabase connection');
        return;
      }
    }
    await markStep(STEPS[currentIdx].id);
    if (currentIdx < STEPS.length - 1) {
      setCurrentIdx(currentIdx + 1);
    } else {
      toast.success('Setup complete! Welcome to WholesaleOS.');
      navigate('/');
    }
  }, [currentIdx, navigate]);

  const handleSkip = useCallback(async () => {
    await markStep(STEPS[currentIdx].id, true);
    if (currentIdx < STEPS.length - 1) setCurrentIdx(currentIdx + 1);
  }, [currentIdx]);

  const handleAutoComplete = useCallback(async () => {
    await markStep(STEPS[currentIdx].id);
  }, [currentIdx]);

  const step = STEPS[currentIdx];
  const StepContent = step.content;
  const progress = Math.round((completedSteps.size / STEPS.length) * 100);

  return (
    <div className="min-h-screen bg-[#F2F4F6] flex">
      {/* Sidebar */}
      <div className="w-64 bg-[#1B3A5C] p-6 flex flex-col">
        <div className="flex items-center gap-2 mb-8">
          <Building2 className="h-7 w-7 text-[#E8720C]" />
          <span className="text-lg font-bold text-white">Setup Wizard</span>
        </div>
        <div className="mb-6">
          <div className="flex justify-between text-xs text-white/60 mb-1">
            <span>Progress</span>
            <span>{progress}%</span>
          </div>
          <div className="h-1.5 bg-white/20 rounded-full overflow-hidden">
            <div className="h-full bg-[#E8720C] rounded-full transition-all duration-500" style={{ width: `${progress}%` }} />
          </div>
        </div>
        <nav className="space-y-1 flex-1">
          {STEPS.map((s, i) => {
            const done = completedSteps.has(s.id);
            const active = i === currentIdx;
            return (
              <button key={s.id} onClick={() => setCurrentIdx(i)}
                className={cn('w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left text-sm transition-colors',
                  active ? 'bg-white/15 text-white' : 'text-white/50 hover:text-white/80 hover:bg-white/5')}>
                <span className="shrink-0">
                  {done ? <CheckCircle className="h-4 w-4 text-green-400" /> : <Circle className="h-4 w-4" />}
                </span>
                <span className="truncate">{s.title}</span>
                {s.optional && !done && <span className="ml-auto text-xs text-white/30">opt</span>}
              </button>
            );
          })}
        </nav>
        <button onClick={() => navigate('/')} className="mt-4 text-xs text-white/40 hover:text-white/70 text-center">
          Skip wizard — configure later
        </button>
      </div>

      {/* Main content */}
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg p-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-[#1B3A5C] text-white rounded-xl">{step.icon}</div>
            <div>
              <h2 className="text-xl font-bold text-gray-900">{step.title}</h2>
              <p className="text-sm text-gray-400">{step.subtitle}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 mb-6">
            <span className="text-xs text-gray-400">Step {currentIdx + 1} of {STEPS.length}</span>
            {step.optional && <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Optional</span>}
          </div>
          {settingsLoaded ? (
            // key forces re-mount when savedSettings first loads so useState
            // initializers in each step receive the correct pre-filled values
            <StepContent key={step.id} onNext={handleNext} onSkip={handleSkip} saved={savedSettings} onAutoComplete={handleAutoComplete} />
          ) : (
            <div className="flex items-center justify-center py-12">
              <div className="h-6 w-6 border-2 border-[#1B3A5C] border-t-transparent rounded-full animate-spin" />
            </div>
          )}
          {currentIdx > 0 && (
            <button onClick={() => setCurrentIdx(currentIdx - 1)} className="flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 mt-4">
              <ChevronLeft className="h-3.5 w-3.5" /> Back
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
