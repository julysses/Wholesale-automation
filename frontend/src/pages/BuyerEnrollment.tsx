import { useCallback, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Button } from '@/components/ui/button';

export type BuyerProgram = { brand: string; support: string; origin: string; disclosure: string; privacy: string; terms: string; version: string };
function capability() {
  const params = new URLSearchParams(window.location.hash.slice(1));
  const token = params.get('token') ?? '', request_id = params.get('reference') ?? '';
  return /^[A-Za-z0-9_-]{43}$/.test(token) && /^[0-9a-f-]{36}$/.test(request_id) ? { token, request_id } : null;
}
async function publicPost(path: string, value: unknown) {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, referrerPolicy: 'no-referrer', body: JSON.stringify(value) });
  const data = await response.json();
  if (!response.ok) throw Object.assign(new Error('Your choice could not be confirmed.'), { status: response.status });
  return data;
}

export function BuyerEnrollment() {
  const location = useLocation();
  return <BuyerEnrollmentForm key={location.pathname + location.hash} />;
}

function BuyerEnrollmentForm() {
  const location = useLocation();
  const [cap] = useState(capability);
  const [receiptReady, setReceiptReady] = useState(!cap);
  const [config, setConfig] = useState<{ available: boolean; program: BuyerProgram | null } | null>(null);
  const [error, setError] = useState('');
  const [phone, setPhone] = useState('');
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Record<string, unknown> | null>(null);
  const [saved, setSaved] = useState<{ accepted: boolean; id: string } | null>(null);
  const validReceipt = useCallback((value: { saved?: boolean; id?: string; accepted?: boolean }) => value.saved === true && value.id === cap?.request_id && typeof value.accepted === 'boolean', [cap]);
  useEffect(() => {
    const controller = new AbortController(); let active = true;
    fetch('/api/buyer-enrollment/config', { signal: controller.signal, referrerPolicy: 'no-referrer' }).then(async response => {
      const value = await response.json();
      if (!response.ok || typeof value.available !== 'boolean' || (value.available && !value.program) || (value.program && ['brand', 'support', 'origin', 'disclosure', 'privacy', 'terms', 'version'].some(k => typeof value.program[k] !== 'string'))) throw new Error();
      if (active) setConfig(value);
    }).catch(() => { if (active) setError('Program details are unavailable. Please try again later.'); });
    if (cap) publicPost('/api/buyer-enrollment/receipt', cap).then(value => {
      if (value.id !== cap.request_id || typeof value.saved !== 'boolean' || (value.saved && !validReceipt(value))) throw new Error();
      if (active) { setReceiptReady(true); if (validReceipt(value)) setSaved(value); }
    }).catch(() => { if (active) setError('A previous choice could not be confirmed. Use the same link and choice when retrying.'); });
    return () => { active = false; controller.abort(); };
  }, [cap, validReceipt]);
  const checkSaved = async () => {
    if (!cap || busy) return; setBusy(true);
    try {
      const value = await publicPost('/api/buyer-enrollment/receipt', cap);
      if (validReceipt(value)) { setSaved(value); setError(''); }
      else if (value.id === cap.request_id && value.saved === false) { setReceiptReady(true); setError('No saved choice is confirmed yet. Retry the same choice or contact support.'); }
      else throw new Error();
    } catch { setError('Your saved choice is unavailable. Keep this same link.'); }
    finally { setBusy(false); }
  };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); if (!cap || !config?.available || !config.program || !receiptReady || busy) return;
    const choice = pending ?? { ...cap, phone, accepted, program_version: config.program.version };
    setPending(choice); setBusy(true); setError('');
    try {
      const value = await publicPost('/api/buyer-enrollment/submit', choice);
      if (!validReceipt(value) || value.accepted !== choice.accepted) throw new Error();
      setSaved(value);
    } catch (failure) {
      if ([409, 422].includes((failure as { status?: number }).status ?? 0)) {
        try {
          const receipt = await publicPost('/api/buyer-enrollment/receipt', cap);
          if (validReceipt(receipt)) { setSaved(receipt); return; }
          if (receipt.id === cap.request_id && receipt.saved === false) {
            setPending(null); setError('Your choice was not saved. Check your number or request a new enrollment link.'); return;
          }
        } catch { /* Keep uncertain requests frozen until their saved receipt can be checked. */ }
      }
      setError('Your choice is unconfirmed. Keep this link and retry the same choice. No confirmation message has been sent.');
    }
    finally { setBusy(false); }
  };
  const program = config?.program;
  const policy = location.pathname.endsWith('/privacy') ? 'privacy' : location.pathname.endsWith('/terms') ? 'terms' : null;
  return <main className="min-h-screen bg-slate-50 px-5 py-12"><div className="mx-auto max-w-2xl rounded-2xl border bg-white p-6 md:p-10 space-y-5">
    <p className="text-sm font-semibold text-slate-600">{program?.brand ?? 'Buyer Deal Alerts'}</p>
    <h1 className="text-3xl font-semibold text-slate-900">{policy === 'privacy' ? 'Buyer SMS Privacy Statement' : policy === 'terms' ? 'Buyer SMS Terms' : 'Choose buyer deal-alert texts'}</h1>
    {error && <p role="alert" className="rounded border border-amber-300 p-3">{error}</p>}
    {!config && !error && <p>Loading program details…</p>}
    {policy ? program ? <><p className="leading-7">{program[policy]}</p><a href="/buyer-sms" className="underline">Back to buyer enrollment</a></> : <p>Program policy details are not available for enrollment.</p> : <>
      {saved ? <div role="status" className="space-y-3"><h2 className="text-xl font-semibold">Your choice is saved</h2>
        <p>{saved.accepted ? 'Your SMS request is saved for review. Messages will start only after your choice, sender approval and activation checks are confirmed.' : 'Buyer SMS remains off. Your choice does not enroll you in text messages.'}</p>
        <p>No confirmation text was sent by this form.</p><p className="text-sm">Receipt: {saved.id}</p></div> : <>
        <p>Receive wholesale property opportunities and availability updates. Texts are optional, and submitting this form does not guarantee activation.</p>
        {!config?.available && <p role="status">Enrollment is currently unavailable. Please contact the program operator.</p>}
        {!cap && <p>Use the private enrollment link supplied by the program operator. This page does not look up or display buyer records.</p>}
        {cap && !receiptReady && <Button disabled={busy} onClick={checkSaved}>Check saved choice</Button>}
        {program && <form onSubmit={submit} className="space-y-5">
          <label className="block font-medium">Your mobile number<input required type="tel" maxLength={32} autoComplete="tel" value={phone} disabled={!!pending || busy || !cap || !config?.available || !receiptReady} onChange={e => setPhone(e.target.value)} className="mt-2 block w-full rounded-lg border p-3" /></label>
          <label className="flex gap-3 items-start"><input type="checkbox" checked={accepted} disabled={!!pending || busy || !cap || !config?.available || !receiptReady} onChange={e => setAccepted(e.target.checked)} className="mt-1" /><span>{program.disclosure}</span></label>
          <p className="text-sm"><a className="underline" href="/buyer-sms/privacy" target="_blank" rel="noopener noreferrer">Privacy Statement</a> · <a className="underline" href="/buyer-sms/terms" target="_blank" rel="noopener noreferrer">Buyer SMS Terms</a></p>
          <Button type="submit" disabled={busy || !cap || !config?.available || !receiptReady}>{pending ? 'Retry saving the same choice' : accepted ? 'Save my SMS request' : 'Keep buyer SMS off'}</Button>
          {pending && <Button type="button" variant="outline" disabled={busy} onClick={checkSaved}>Check saved choice</Button>}
        </form>}
      </>}
      {program && <><p className="text-sm">For support: {program.support}. Reply STOP to opt out of messages or HELP for help.</p><details className="text-sm"><summary>About this program</summary><p>{program.terms}</p><p>{program.privacy}</p></details></>}
    </>}
  </div></main>;
}
