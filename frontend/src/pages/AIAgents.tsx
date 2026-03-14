import { useState } from 'react';
import { useLeads } from '@/hooks/useLeads';
import { useDeals } from '@/hooks/useDeals';
import { useLeadQualifier, useOfferGenerator, useOutreachWriter, useBuyerMatcher } from '@/hooks/useAIAgent';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Select } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { formatCurrency } from '@/lib/utils';
import { Bot, Zap, MessageSquare, Users, ChevronDown, ChevronUp, Copy, Check, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button onClick={copy} className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors">
      {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1 px-3 py-2">
      {[0, 1, 2].map((i) => (
        <span key={i} className="h-2 w-2 bg-[#E8720C] rounded-full animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }} />
      ))}
      <span className="text-xs text-gray-400 ml-2">Claude is thinking...</span>
    </div>
  );
}

export function AIAgents() {
  const { data: leadsData } = useLeads({ pageSize: 100 });
  const { data: deals = [] } = useDeals();
  const leads = leadsData?.data ?? [];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">AI Agents</h1>
        <p className="text-sm text-gray-500 mt-0.5">Claude-powered tools for qualifying, offering, outreach, and buyer matching</p>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <LeadQualifierPanel leads={leads} />
        <OfferGeneratorPanel leads={leads} />
        <OutreachWriterPanel leads={leads} />
        <BuyerMatcherPanel deals={deals} />
      </div>
    </div>
  );
}

// ─── Agent 1: Lead Qualifier ──────────────────────────────────────────────────
function LeadQualifierPanel({ leads }: { leads: any[] }) {
  const [leadId, setLeadId] = useState('');
  const [notes, setNotes] = useState('');
  const { qualify, loading, result, error } = useLeadQualifier();

  const selectedLead = leads.find((l) => l.id === leadId);

  const handleRun = () => {
    if (!leadId) return toast.error('Select a lead');
    qualify({
      lead_id: leadId,
      property_address: selectedLead?.property_address || '',
      seller_notes: notes || selectedLead?.seller_notes || '',
      estimated_equity_pct: selectedLead?.estimated_equity_pct,
    });
  };

  const tierColor = result?.tier === 'HOT' ? 'bg-red-500' : result?.tier === 'WARM' ? 'bg-yellow-500' : 'bg-blue-500';

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="p-2 bg-orange-50 rounded-lg"><Bot className="h-5 w-5 text-[#E8720C]" /></div>
          <div>
            <CardTitle>Lead Qualifier</CardTitle>
            <p className="text-xs text-gray-400 mt-0.5">Score motivation, timeline, equity, condition, flexibility</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <Select
          label="Select Lead"
          value={leadId}
          onChange={(e) => setLeadId(e.target.value)}
          options={leads.map((l) => ({ value: l.id, label: `${l.property_address} — ${l.owner_first_name || ''} ${l.owner_last_name || ''}`.trim() }))}
          placeholder="Choose a lead..."
        />
        <Textarea
          label="Seller Conversation Notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Paste call transcript or notes about the seller conversation..."
          rows={4}
        />
        <Button onClick={handleRun} loading={loading} className="w-full" icon={<Zap className="h-4 w-4" />}>
          Run Qualifier
        </Button>

        {loading && <TypingIndicator />}
        {error && <p className="text-sm text-red-500 bg-red-50 p-3 rounded-lg">{error}</p>}

        {result && !loading && (
          <div className="space-y-4 border-t border-gray-100 pt-4">
            {/* Tier badge */}
            <div className="flex items-center gap-3">
              <span className={cn('px-4 py-1.5 rounded-full text-white text-sm font-bold', tierColor)}>
                {result.tier}
              </span>
              <span className="text-lg font-bold text-gray-900">{result.total_score}/15</span>
            </div>

            {/* Score breakdown */}
            <div className="grid grid-cols-5 gap-2">
              {[
                ['Motivation', result.score_motivation],
                ['Timeline', result.score_timeline],
                ['Equity', result.score_equity],
                ['Condition', result.score_condition],
                ['Flexibility', result.score_flexibility],
              ].map(([label, score]) => (
                <div key={String(label)} className="text-center">
                  <div className={cn('mx-auto w-10 h-10 rounded-full flex items-center justify-center text-lg font-bold text-white',
                    Number(score) === 3 ? 'bg-green-500' : Number(score) === 2 ? 'bg-yellow-500' : 'bg-red-400'
                  )}>
                    {score}
                  </div>
                  <p className="text-xs text-gray-400 mt-1 leading-tight">{label}</p>
                </div>
              ))}
            </div>

            {/* Summary */}
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-sm text-gray-700">{result.qualification_summary}</p>
            </div>

            {/* Next action */}
            <div className="bg-[#1B3A5C] text-white rounded-lg p-3">
              <p className="text-xs font-medium opacity-70 mb-1">RECOMMENDED NEXT ACTION</p>
              <p className="text-sm">{result.recommended_next_action}</p>
            </div>

            {/* Risks */}
            {result.key_risks?.length > 0 && (
              <div className="space-y-1">
                <p className="text-xs font-medium text-gray-500">KEY RISKS</p>
                {result.key_risks.map((r, i) => (
                  <p key={i} className="text-xs text-red-600 bg-red-50 px-2 py-1 rounded">⚠ {r}</p>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Agent 2: Offer Generator ─────────────────────────────────────────────────
function OfferGeneratorPanel({ leads }: { leads: any[] }) {
  const [leadId, setLeadId] = useState('');
  const [arv, setArv] = useState('');
  const [repairs, setRepairs] = useState('');
  const [fee, setFee] = useState('15000');
  const { generate, loading, result, error } = useOfferGenerator();

  const selectedLead = leads.find((l) => l.id === leadId);

  const mao = arv && repairs && fee
    ? Number(arv) * 0.7 - Number(repairs) - Number(fee)
    : selectedLead?.mao;

  const handleRun = () => {
    if (!leadId) return toast.error('Select a lead');
    generate({
      lead_id: leadId,
      property_address: selectedLead?.property_address || '',
      ai_qualification_summary: selectedLead?.ai_qualification_summary || '',
      motivation_tag: selectedLead?.motivation_tag || '',
      asking_price: selectedLead?.asking_price,
      mao: mao || undefined,
      arv: arv ? Number(arv) : selectedLead?.estimated_arv,
      repair_estimate: repairs ? Number(repairs) : selectedLead?.estimated_repairs,
    });
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="p-2 bg-blue-50 rounded-lg"><Zap className="h-5 w-5 text-blue-600" /></div>
          <div>
            <CardTitle>Offer Generator</CardTitle>
            <p className="text-xs text-gray-400 mt-0.5">Generate 3 strategic offer options with objection scripts</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <Select label="Select Lead" value={leadId}
          onChange={(e) => setLeadId(e.target.value)}
          options={leads.map((l) => ({ value: l.id, label: l.property_address }))}
          placeholder="Choose a lead..." />
        <div className="grid grid-cols-3 gap-2">
          <Input label="ARV" type="number" value={arv} onChange={(e) => setArv(e.target.value)} placeholder="e.g. 250000" />
          <Input label="Repairs" type="number" value={repairs} onChange={(e) => setRepairs(e.target.value)} placeholder="e.g. 35000" />
          <Input label="Fee Target" type="number" value={fee} onChange={(e) => setFee(e.target.value)} />
        </div>
        {mao && <p className="text-sm text-gray-500">Calculated MAO: <span className="font-bold text-[#1B3A5C]">{formatCurrency(mao)}</span></p>}
        <Button onClick={handleRun} loading={loading} className="w-full" icon={<Zap className="h-4 w-4" />}>
          Generate Offer Options
        </Button>

        {loading && <TypingIndicator />}
        {error && <p className="text-sm text-red-500 bg-red-50 p-3 rounded-lg">{error}</p>}

        {result && !loading && (
          <div className="space-y-4 border-t border-gray-100 pt-4">
            {/* Offer options */}
            {result.options?.map((opt, i) => (
              <div key={i} className="border border-gray-200 rounded-xl p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-gray-900">{opt.name}</span>
                  <span className="text-lg font-bold text-[#1B3A5C]">{formatCurrency(opt.offer_price)}</span>
                </div>
                <p className="text-xs text-gray-400">Close in {opt.close_timeline}</p>
                <div className="space-y-1">
                  {(opt.selling_points || []).map((point, j) => (
                    <p key={j} className="text-xs text-gray-600">✓ {point}</p>
                  ))}
                </div>
                <div className="bg-blue-50 rounded-lg p-2 flex items-start justify-between gap-2">
                  <p className="text-xs text-blue-700 italic">"{opt.pitch}"</p>
                  <CopyButton text={opt.pitch} />
                </div>
              </div>
            ))}

            {/* Objections */}
            {result.objections?.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-gray-500 uppercase">Objection Handling</p>
                {result.objections.map((obj, i) => (
                  <div key={i} className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 space-y-1">
                    <p className="text-xs font-medium text-yellow-800">"{obj.objection}"</p>
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs text-gray-700">{obj.script}</p>
                      <CopyButton text={obj.script} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Agent 3: Outreach Writer ─────────────────────────────────────────────────
function OutreachWriterPanel({ leads }: { leads: any[] }) {
  const [leadId, setLeadId] = useState('');
  const [channel, setChannel] = useState('sms');
  const [tone, setTone] = useState('Friendly');
  const { write, loading, result, error } = useOutreachWriter();

  const selectedLead = leads.find((l) => l.id === leadId);

  const handleRun = () => {
    if (!leadId) return toast.error('Select a lead');
    write({
      lead_id: leadId,
      property_address: selectedLead?.property_address || '',
      city: selectedLead?.city || '',
      owner_first_name: selectedLead?.owner_first_name || '',
      motivation_tag: selectedLead?.motivation_tag || '',
      contact_attempts: selectedLead?.contact_attempts || 1,
      channel,
      tone,
    });
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="p-2 bg-purple-50 rounded-lg"><MessageSquare className="h-5 w-5 text-purple-600" /></div>
          <div>
            <CardTitle>Outreach Writer</CardTitle>
            <p className="text-xs text-gray-400 mt-0.5">Generate personalized SMS, email, voicemail & direct mail</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <Select label="Select Lead" value={leadId}
          onChange={(e) => setLeadId(e.target.value)}
          options={leads.map((l) => ({ value: l.id, label: l.property_address }))}
          placeholder="Choose a lead..." />
        <div className="grid grid-cols-2 gap-3">
          <Select label="Channel" value={channel}
            onChange={(e) => setChannel(e.target.value)}
            options={[
              { value: 'sms', label: 'SMS' },
              { value: 'email', label: 'Email' },
              { value: 'voicemail', label: 'Voicemail Script' },
              { value: 'direct_mail', label: 'Direct Mail' },
            ]} />
          <Select label="Tone" value={tone}
            onChange={(e) => setTone(e.target.value)}
            options={[
              { value: 'Friendly', label: 'Friendly' },
              { value: 'Professional', label: 'Professional' },
              { value: 'Urgent', label: 'Urgent' },
            ]} />
        </div>
        <Button onClick={handleRun} loading={loading} className="w-full" icon={<MessageSquare className="h-4 w-4" />}>
          Generate Copy
        </Button>

        {loading && <TypingIndicator />}
        {error && <p className="text-sm text-red-500 bg-red-50 p-3 rounded-lg">{error}</p>}

        {result && !loading && (
          <div className="space-y-3 border-t border-gray-100 pt-4">
            <p className="text-xs font-semibold text-gray-500 uppercase">3 Variations</p>
            {result.map((v, i) => (
              <div key={i} className="border border-gray-200 rounded-xl p-4 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-gray-500">VARIATION {i + 1}</span>
                  <CopyButton text={v.subject ? `${v.subject}\n\n${v.body}` : v.body} />
                </div>
                {v.subject && (
                  <p className="text-xs font-medium text-gray-700 bg-gray-50 px-2 py-1 rounded">
                    Subject: {v.subject}
                  </p>
                )}
                <p className="text-sm text-gray-800 whitespace-pre-line leading-relaxed">{v.body}</p>
                {channel === 'sms' && (
                  <p className="text-xs text-gray-400">{v.body.length} chars</p>
                )}
                <p className="text-xs text-blue-600 bg-blue-50 px-2 py-1 rounded">
                  💡 {v.estimated_response_rate_notes}
                </p>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ─── Agent 4: Buyer Matcher ───────────────────────────────────────────────────
function BuyerMatcherPanel({ deals }: { deals: any[] }) {
  const [dealId, setDealId] = useState('');
  const { match, loading, result, error } = useBuyerMatcher();

  const selectedDeal = deals.find((d) => d.id === dealId);

  const handleRun = () => {
    if (!dealId) return toast.error('Select a deal');
    match({
      deal_id: dealId,
      property_address: selectedDeal?.lead?.property_address || selectedDeal?.deal_name || '',
      contract_price: selectedDeal?.contract_price,
      buyer_price: selectedDeal?.buyer_price,
      arv: selectedDeal?.arv,
      repair_estimate: selectedDeal?.repair_estimate,
      zip_code: selectedDeal?.lead?.zip_code,
      closing_date: selectedDeal?.closing_date,
    });
  };

  const activeDeal = deals.filter((d) => !['closed', 'cancelled'].includes(d.stage));

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="p-2 bg-green-50 rounded-lg"><Users className="h-5 w-5 text-green-600" /></div>
          <div>
            <CardTitle>Buyer Matcher</CardTitle>
            <p className="text-xs text-gray-400 mt-0.5">Match deals to buyers & generate blast templates</p>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <Select label="Select Deal" value={dealId}
          onChange={(e) => setDealId(e.target.value)}
          options={activeDeal.map((d) => ({
            value: d.id,
            label: d.lead?.property_address || d.deal_name || d.id,
          }))}
          placeholder="Choose a deal..." />
        <Button onClick={handleRun} loading={loading} className="w-full" icon={<Users className="h-4 w-4" />}>
          Find Matching Buyers
        </Button>

        {loading && <TypingIndicator />}
        {error && <p className="text-sm text-red-500 bg-red-50 p-3 rounded-lg">{error}</p>}

        {result && !loading && (
          <div className="space-y-4 border-t border-gray-100 pt-4">
            <p className="text-sm font-semibold text-gray-700">
              {result.ranked_buyers?.length || 0} buyers matched
            </p>

            {/* Ranked buyers */}
            <div className="space-y-2 max-h-56 overflow-y-auto">
              {(result.ranked_buyers || []).map((m, i) => (
                <div key={i} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
                  <div className="text-center shrink-0 w-10">
                    <p className="text-xs text-gray-400">#{i + 1}</p>
                    <p className={cn('text-sm font-bold',
                      m.fit_score >= 80 ? 'text-green-600' :
                      m.fit_score >= 60 ? 'text-yellow-600' : 'text-gray-500'
                    )}>{m.fit_score}%</p>
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900">
                      {m.buyer?.first_name} {m.buyer?.last_name}
                      {m.buyer?.company && <span className="text-gray-400 font-normal"> · {m.buyer.company}</span>}
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">{m.fit_reason}</p>
                    {m.personalization_tip && (
                      <p className="text-xs text-blue-600 mt-1">💡 {m.personalization_tip}</p>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Blast templates */}
            {result.blast_email_subject && (
              <div className="space-y-2">
                <p className="text-xs font-semibold text-gray-500 uppercase">Blast Templates</p>
                <div className="border border-gray-200 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-xs font-medium text-gray-500">EMAIL</p>
                    <CopyButton text={`${result.blast_email_subject}\n\n${result.blast_email_body}`} />
                  </div>
                  <p className="text-xs font-semibold text-gray-800 mb-1">{result.blast_email_subject}</p>
                  <p className="text-xs text-gray-600">{result.blast_email_body}</p>
                </div>
                <div className="border border-gray-200 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-xs font-medium text-gray-500">SMS ({result.blast_sms?.length || 0} chars)</p>
                    <CopyButton text={result.blast_sms || ''} />
                  </div>
                  <p className="text-sm text-gray-700">{result.blast_sms}</p>
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
