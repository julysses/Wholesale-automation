import { apiFetch } from '@/lib/api';
/**
 * OutreachLauncher — SMS and email blast to matched buyer IDs.
 *
 * Usage:
 *   <OutreachLauncher
 *     buyerIds={selectedIds}
 *     deal={{ property_address, zip_code, price, arv, ... }}
 *     onSent={() => refetch()}
 *   />
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { MessageSquare, Mail, Send, CheckCircle2 } from 'lucide-react';
import { toast } from 'sonner';

interface DealContext {
  deal_id?: string;
  property_address?: string;
  zip_code?: string;
  price?: number;
  arv?: number;
  assignment_fee?: number;
  property_type?: string;
  beds?: number;
  baths?: number;
  condition?: string;
}

interface OutreachLauncherProps {
  buyerIds: string[];
  deal?: DealContext;
  onSent?: () => void;
}

type Channel = 'sms' | 'email';
type Status  = 'idle' | 'sending' | 'done';

// Auto-generate default messages for preview
function defaultSms(deal: DealContext): string {
  const zip   = deal.zip_code   || 'the area';
  const price = deal.price ? `$${deal.price.toLocaleString()}` : 'TBD';
  const desc  = deal.beds ? `${deal.beds}bd/${deal.baths}ba ${deal.property_type || 'property'}` : (deal.property_type || 'property');
  return `Hey, I've got an off-market ${desc} in ${zip} — asking ${price}. Want details?`;
}

function defaultEmailSubject(deal: DealContext): string {
  const zip   = deal.zip_code || 'your market';
  const price = deal.price ? `$${deal.price.toLocaleString()}` : 'TBD';
  const desc  = deal.beds ? `${deal.beds}bd/${deal.baths}ba ` : '';
  return `Off-Market: ${desc}${deal.property_type || 'Property'} in ${zip} — ${price}`;
}

function defaultEmailBody(deal: DealContext): string {
  const addr  = deal.property_address || 'Address withheld';
  const price = deal.price ? `$${deal.price.toLocaleString()}` : 'TBD';
  const arv   = deal.arv ? `$${deal.arv.toLocaleString()}` : 'TBD';
  const fee   = deal.assignment_fee ? `$${deal.assignment_fee.toLocaleString()}` : 'TBD';
  const cond  = deal.condition ? deal.condition.replace(/_/g, ' ') : 'TBD';
  return `Hi,

I have an off-market deal that matches your buy box:

  Address:         ${addr}
  Price:           ${price}
  ARV:             ${arv}
  Assignment Fee:  ${fee}
  Condition:       ${cond}

Reply or call to get photos, comps, and full details. This one moves fast.`;
}

export function OutreachLauncher({ buyerIds, deal = {}, onSent }: OutreachLauncherProps) {
  const [channel, setChannel] = useState<Channel>('sms');
  const [smsBody, setSmsBody] = useState(() => defaultSms(deal));
  const [emailSubject, setEmailSubject] = useState(() => defaultEmailSubject(deal));
  const [emailBody, setEmailBody] = useState(() => defaultEmailBody(deal));
  const [status, setStatus] = useState<Status>('idle');
  const [sentCount, setSentCount] = useState(0);

  const handleSend = async () => {
    if (buyerIds.length === 0) return toast.error('No buyers selected');
    setStatus('sending');

    try {
      const endpoint = `/api/buyers/outreach/${channel}`;
      const payload = {
        buyer_ids:       buyerIds,
        deal_id:         deal.deal_id,
        property_address: deal.property_address || '',
        zip_code:        deal.zip_code || '',
        price:           deal.price || 0,
        arv:             deal.arv || 0,
        assignment_fee:  deal.assignment_fee || 0,
        property_type:   deal.property_type || '',
        beds:            deal.beds || 0,
        baths:           deal.baths || 0,
        condition:       deal.condition || '',
        custom_message:  channel === 'sms' ? smsBody : '',
      };

      const resp = await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) throw new Error(await resp.text());

      setSentCount(buyerIds.length);
      setStatus('done');
      toast.success(`${channel.toUpperCase()} blast queued for ${buyerIds.length} buyers`);
      onSent?.();
    } catch (err) {
      toast.error(`Send failed: ${err}`);
      setStatus('idle');
    }
  };

  if (status === 'done') {
    return (
      <div className="flex flex-col items-center gap-3 py-6">
        <CheckCircle2 className="h-12 w-12 text-green-500" />
        <p className="font-semibold text-gray-700">
          {channel.toUpperCase()} blast sent to {sentCount} buyers
        </p>
        <Button variant="outline" size="sm" onClick={() => setStatus('idle')}>
          Send Another
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Channel toggle */}
      <div className="flex rounded-lg border border-gray-200 overflow-hidden w-fit">
        {(['sms', 'email'] as Channel[]).map((ch) => (
          <button
            key={ch}
            onClick={() => setChannel(ch)}
            className={cn(
              'flex items-center gap-2 px-4 py-2 text-sm font-medium transition-colors',
              channel === ch
                ? 'bg-[#1B3A5C] text-white'
                : 'bg-white text-gray-600 hover:bg-gray-50'
            )}
          >
            {ch === 'sms'
              ? <MessageSquare className="h-4 w-4" />
              : <Mail className="h-4 w-4" />}
            {ch.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Recipients badge */}
      <p className="text-sm text-gray-600">
        Sending to <span className="font-semibold text-[#E8720C]">{buyerIds.length} buyers</span>
      </p>

      {/* SMS compose */}
      {channel === 'sms' && (
        <div className="space-y-2">
          <Textarea
            label="SMS Message"
            value={smsBody}
            onChange={(e) => setSmsBody(e.target.value)}
            rows={3}
            placeholder="Your message…"
          />
          <p className="text-xs text-gray-400 text-right">{smsBody.length}/160 chars</p>
          <p className="text-xs text-gray-400">
            Personalization: buyer's first name is automatically prepended by the system.
          </p>
        </div>
      )}

      {/* Email compose */}
      {channel === 'email' && (
        <div className="space-y-3">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Subject</label>
            <input
              type="text"
              value={emailSubject}
              onChange={(e) => setEmailSubject(e.target.value)}
              className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#1B3A5C]"
            />
          </div>
          <Textarea
            label="Email Body"
            value={emailBody}
            onChange={(e) => setEmailBody(e.target.value)}
            rows={10}
          />
          <p className="text-xs text-gray-400">
            HTML formatting is supported. An unsubscribe footer is automatically appended.
          </p>
        </div>
      )}

      <Button onClick={handleSend} loading={status === 'sending'} className="w-full">
        <Send className="h-4 w-4 mr-2" />
        Send {channel.toUpperCase()} to {buyerIds.length} Buyers
      </Button>
    </div>
  );
}
