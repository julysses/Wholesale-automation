import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { useParams } from 'react-router-dom';
import { CheckCircle2, ChevronLeft, ChevronRight, Home, Loader2 } from 'lucide-react';
import { SellerChallenge } from '@/components/seller/SellerChallenge';
import { clearSellerInquiry, matchesSellerReceipt, preserveSellerInquiry, readSellerInquiry, sellerDisplaySchema, sellerInquirySchema,
  UNCONFIRMED_SELLER_REQUEST, type PendingSellerInquiry, type SellerDisplay } from '@/lib/sellerOfferRequest';

const steps = ['Property', 'Your plans', 'Contact', 'Review'];
const labels: Record<string, string> = { owner: 'Owner', authorized_representative: 'Authorized representative', not_authorized: 'Not authorized', unsure: 'Not sure', move_in_ready: 'Move-in ready', cosmetic_repairs: 'Cosmetic repairs', major_repairs: 'Major repairs', owner_occupied: 'Owner occupied', tenant_occupied: 'Tenant occupied', vacant: 'Vacant', other: 'Other', within_30_days: 'Within 30 days', one_to_three_months: '1–3 months', three_to_six_months: '3–6 months', flexible: 'Flexible' };
const inputClass = 'mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-3 text-base text-slate-900 focus:outline-none focus:ring-2 focus:ring-[#E8720C] disabled:bg-slate-100';
const primary = 'inline-flex items-center justify-center gap-2 rounded-lg bg-[#1B3A5C] px-5 py-3 font-semibold text-white focus:outline-none focus:ring-2 focus:ring-[#E8720C] focus:ring-offset-2 disabled:opacity-50';
const initial = { address: '', city: '', state: 'TX', postal_code: '', authority: '', condition: '', occupancy: '', timeline: '', motivation: '', asking_price: '', name: '', phone: '', email: '' };
type Answers = typeof initial;

export function SellerOffer() {
  const { formKey = '' } = useParams<{ formKey: string }>();
  return <SellerOfferForm key={formKey} formKey={formKey} />;
}

export function SellerOfferForm({ formKey }: { formKey: string }) {
  const [recovery] = useState(() => {
    try { return { pending: readSellerInquiry(window.sessionStorage, formKey), blocked: false }; }
    catch { return { pending: null, blocked: true }; }
  });
  const [pending, setPending] = useState(recovery.pending);
  const [display, setDisplay] = useState<SellerDisplay | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const [error, setError] = useState('');
  const [blocked, setBlocked] = useState(recovery.blocked);
  const [step, setStep] = useState(recovery.pending ? 4 : 1);
  const [answers, setAnswers] = useState<Answers>(initial);
  const [privacy, setPrivacy] = useState(false);
  const [callback, setCallback] = useState(false);
  const [emailReply, setEmailReply] = useState(false);
  const [inquiryId] = useState(() => recovery.pending?.inquiry.submission_id || crypto.randomUUID());
  const [token, setToken] = useState<string | null>(null);
  const [challenge, setChallenge] = useState(0);
  const [busy, setBusy] = useState(false);
  const [received, setReceived] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const lock = useRef(false);
  const title = useRef<HTMLHeadingElement>(null);
  const controller = useRef<AbortController | null>(null);
  const onToken = useCallback((value: string | null) => setToken(value), []);

  useEffect(() => {
    const abort = new AbortController(); let active = true;
    const timeout = window.setTimeout(() => abort.abort(), 15000);
    setLoading(true); setError(''); setDisplay(null);
    void fetch(`/api/acquisition/portal/${encodeURIComponent(formKey)}`, { signal: abort.signal, cache: 'no-store', credentials: 'omit' })
      .then(async response => {
        if (!response.ok) throw new Error(response.status === 404 ? 'This offer request form is not available right now.' : 'We could not load this form. Please try again.');
        const result = sellerDisplaySchema.parse(await response.json());
        if (result.definition.form_key !== formKey) throw new Error('This form could not be verified.');
        if (active) setDisplay(result);
      }).catch(caught => { if (active) setError(caught instanceof Error && caught.name !== 'AbortError' && !('issues' in caught)
        ? caught.message : 'We could not load this form. Please try again.'); })
      .finally(() => { window.clearTimeout(timeout); if (active) setLoading(false); });
    return () => { active = false; abort.abort(); window.clearTimeout(timeout); };
  }, [formKey, loadAttempt]);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(() => { title.current?.focus(); }, [step]);
  useEffect(() => {
    if (!cooldown) return;
    const timer = window.setTimeout(() => setCooldown(value => Math.max(0, value - 1)), 1000);
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  const definition = pending?.definition || display?.definition;
  const definitionChanged = !!(pending && display && JSON.stringify(pending.definition) !== JSON.stringify(display.definition));
  const field = (name: keyof Answers, label: string, options?: [string, string][], type = 'text') => <label className="block text-sm font-medium text-[#1B3A5C]" key={name}>
    {label}{options ? <select className={inputClass} value={answers[name]} required onChange={event => setAnswers(value => ({ ...value, [name]: name === 'state' ? event.target.value.toUpperCase() : event.target.value }))}>
      <option value="">Select an option</option>{options.map(([value, text]) => <option value={value} key={value}>{text}</option>)}
    </select> : <input className={inputClass} type={type} value={answers[name]} required={!['asking_price', 'phone', 'email'].includes(name)} maxLength={name === 'motivation' ? 2000 : name === 'email' ? 254 : name === 'state' ? 2 : name === 'postal_code' ? 10 : name === 'phone' ? 40 : 200}
      onChange={event => setAnswers(value => ({ ...value, [name]: name === 'state' ? event.target.value.toUpperCase() : event.target.value }))} />}
  </label>;

  function proposed() {
    return sellerInquirySchema.safeParse({ submission_id: inquiryId, form_version: display?.definition.version,
      seller: { name: answers.name.trim(), phone: answers.phone.trim() || null, email: answers.email.trim() || null },
      property: { ...Object.fromEntries(['address', 'city', 'state', 'postal_code', 'authority', 'condition', 'occupancy', 'timeline', 'motivation'].map(key => [key, answers[key as keyof Answers].trim()])), asking_price: answers.asking_price.trim() || null },
      selections: { privacy_acknowledged: privacy, human_callback_requested: callback, email_reply_requested: emailReply } });
  }
  function next(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('');
    if (step === 1 && (!answers.address.trim() || !answers.city.trim())) { setError('Enter the property street address and city.'); return; }
    if (step === 1 && (!/^[A-Z]{2}$/.test(answers.state) || !/^\d{5}(?:-\d{4})?$/.test(answers.postal_code))) {
      setError('Enter a two-letter state and a valid ZIP code.'); return;
    }
    if (step === 2 && answers.asking_price && (!/^(?:0|[1-9]\d{0,9})(?:\.\d{1,2})?$/.test(answers.asking_price) || Number(answers.asking_price) > 1000000000)) {
      setError('Enter your asking price using numbers, without commas, or leave it blank.'); return;
    }
    if (step === 3) {
      const parsed = proposed();
      if (!parsed.success) { setError('Review your name, contact information and acknowledgement. Select a phone number for callbacks or an email address for email replies.'); return; }
    }
    setToken(null); setStep(value => value + 1);
  }
  async function submit() {
    if (lock.current || !token || !display || blocked || definitionChanged || cooldown) return;
    lock.current = true; setBusy(true); setError('');
    let saved: PendingSellerInquiry;
    try {
      if (pending) saved = pending;
      else {
        const parsed = proposed();
        if (!parsed.success) throw new Error('Review your details before submitting.');
        saved = preserveSellerInquiry(window.sessionStorage, { version: 1, formKey, savedAt: new Date().toISOString(), definition: display.definition, inquiry: parsed.data });
        setPending(saved);
      }
    } catch {
      setBlocked(true); setError('We could not safely save this request in your browser. No new request was sent.');
      setBusy(false); lock.current = false; return;
    }
    const abort = new AbortController(); controller.current = abort;
    const timeout = window.setTimeout(() => abort.abort(), 60000);
    try {
      const response = await fetch(`/api/acquisition/portal/${encodeURIComponent(formKey)}`, { method: 'POST', signal: abort.signal,
        credentials: 'omit', cache: 'no-store', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ inquiry: saved.inquiry, bot_token: token }) });
      if (!response.ok) {
        if (response.status === 429) setCooldown(Math.max(1, Math.min(60, Number(response.headers.get('Retry-After')) || 10)));
        throw new Error(UNCONFIRMED_SELLER_REQUEST);
      }
      const receipt: unknown = await response.json();
      if (!matchesSellerReceipt(receipt, saved)) throw new Error(UNCONFIRMED_SELLER_REQUEST);
      try { clearSellerInquiry(window.sessionStorage, saved, receipt); }
      catch { setError('Your request was received. A saved copy remains in this browser.'); }
      setReceived(true);
    } catch { setError(UNCONFIRMED_SELLER_REQUEST); }
    finally { window.clearTimeout(timeout); controller.current = null; setBusy(false); lock.current = false; setToken(null); setChallenge(value => value + 1); }
  }
  const currentProposal = proposed();
  const review = pending?.inquiry || (currentProposal.success ? currentProposal.data : null);

  return <main className="min-h-screen bg-[#F2F4F6] px-4 py-8 sm:py-12 text-slate-800">
    <div className="mx-auto max-w-2xl space-y-6">
      <header className="flex items-center gap-3 text-[#1B3A5C]"><span className="rounded-xl bg-[#1B3A5C] p-3 text-[#E8720C]"><Home aria-hidden="true" /></span><div><p className="text-lg font-bold">Hilltop Home Company</p><p className="text-sm">A clear next step for your property</p></div></header>
      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-8">
        {received ? <div className="space-y-4 text-center" role="status"><CheckCircle2 className="mx-auto h-12 w-12 text-[#E8720C]" /><h1 className="text-2xl font-bold text-[#1B3A5C]">Your request is received</h1><p>Hilltop will review your property and the details you shared. This confirmation is not a purchase offer.</p>{error && <p className="text-sm">{error}</p>}</div>
          : loading ? <p role="status" className="flex items-center gap-2"><Loader2 className="animate-spin" /> Loading your request form…</p>
          : !display ? <div className="space-y-4"><h1 className="text-2xl font-bold text-[#1B3A5C]">Request an offer</h1><p role="alert">{error}</p><button className={primary} onClick={() => setLoadAttempt(value => value + 1)}>Try again</button></div>
          : <>
            <h1 className="text-2xl font-bold text-[#1B3A5C]">Tell us about your property</h1><p className="mt-2 text-sm text-slate-600">Share a few details for Hilltop to review. There is no obligation and no instant binding offer.</p>
            <ol aria-label="Offer request steps" className="my-6 grid grid-cols-4 gap-2">{steps.map((label, index) => <li key={label} aria-current={step === index + 1 ? 'step' : undefined} className={`rounded-lg px-2 py-3 text-center text-xs sm:text-sm ${step === index + 1 ? 'bg-[#1B3A5C] text-white' : 'bg-slate-100 text-slate-600'}`}><span className={`block font-bold ${step === index + 1 ? 'text-[#E8720C]' : 'text-[#1B3A5C]'}`}>{index + 1}</span>{label}</li>)}</ol>
            <h2 ref={title} tabIndex={-1} className="mb-4 text-lg font-bold text-[#1B3A5C] focus:outline-none">Step {step} of 4 · {steps[step - 1]}</h2>
            {error && <p role="alert" className="mb-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-950">{error}</p>}
            {blocked ? <p role="alert">A saved request could not be read or preserved safely. We have kept it unchanged. Contact Hilltop before starting another request.</p>
              : definitionChanged ? <div role="alert"><p>The form has changed. Your saved request is unchanged; contact Hilltop before starting another inquiry.</p><button className={`${primary} mt-4`} onClick={() => setLoadAttempt(value => value + 1)}>Refresh form</button></div>
              : step < 4 ? <form onSubmit={next} className="space-y-4">
                {step === 1 && <>{field('address', 'Street address, including unit if applicable')}
                  <div className="grid gap-4 sm:grid-cols-3">{field('city', 'City')}{field('state', 'State')}{field('postal_code', 'ZIP code')}</div>
                  {field('authority', 'Your relationship to the property', [['owner', 'I own the property'], ['authorized_representative', 'I am authorized to discuss it'], ['unsure', 'I am not sure'], ['not_authorized', 'I am not authorized']])}
                  <p className="text-sm text-slate-500">We will verify the property details during review.</p></>}
                {step === 2 && <>{field('condition', 'Current condition', [['move_in_ready', 'Move-in ready'], ['cosmetic_repairs', 'Cosmetic repairs'], ['major_repairs', 'Major repairs'], ['unsure', 'Not sure']])}
                  {field('occupancy', 'Who is living there?', [['owner_occupied', 'Owner'], ['tenant_occupied', 'Tenant'], ['vacant', 'Vacant'], ['other', 'Other'], ['unsure', 'Not sure']])}
                  {field('timeline', 'When would you like to sell?', [['within_30_days', 'Within 30 days'], ['one_to_three_months', '1–3 months'], ['three_to_six_months', '3–6 months'], ['flexible', 'Flexible'], ['unsure', 'Not sure']])}
                  {field('motivation', 'What would you like us to know?')}{field('asking_price', 'Asking price (optional, without commas)')}</>}
                {step === 3 && <>{field('name', 'Your name')}{field('phone', 'Phone number (optional)', undefined, 'tel')}{field('email', 'Email address (optional)', undefined, 'email')}
                  <p className="text-sm text-slate-500">Provide at least one way to reach you.</p>
                  <label className="flex gap-3 text-sm"><input type="checkbox" required checked={privacy} onChange={event => setPrivacy(event.target.checked)} />{definition?.privacy_acknowledged}</label>
                  <label className="flex gap-3 text-sm"><input type="checkbox" checked={callback} onChange={event => setCallback(event.target.checked)} />{definition?.human_callback_requested}</label>
                  <label className="flex gap-3 text-sm"><input type="checkbox" checked={emailReply} onChange={event => setEmailReply(event.target.checked)} />{definition?.email_reply_requested}</label></>}
                <div className="flex justify-between gap-3 pt-4">{step > 1 ? <button type="button" className="flex items-center gap-1 px-3 py-3" onClick={() => { setError(''); setStep(value => value - 1); }}><ChevronLeft size={18} />Back</button> : <span />}
                  <button className={primary} type="submit">{step === 3 ? 'Review request' : 'Continue'}<ChevronRight size={18} /></button></div>
              </form> : <div className="space-y-5">
                {pending && <p className="rounded-lg bg-slate-100 p-3 text-sm">Your original request is saved. Retry these same details to confirm receipt.</p>}
                {review && <dl className="space-y-3 rounded-xl bg-slate-50 p-4 text-sm">
                  <div><dt className="font-semibold">Property</dt><dd>{review.property.address}, {review.property.city}, {review.property.state} {review.property.postal_code}</dd><dd>{labels[review.property.authority]}</dd></div>
                  <div><dt className="font-semibold">Your plans</dt><dd>{labels[review.property.condition]} · {labels[review.property.occupancy]}</dd><dd>Timing: {labels[review.property.timeline]}</dd><dd>{review.property.motivation}</dd><dd>Asking price: {review.property.asking_price ?? 'Not provided'}</dd></div>
                  <div><dt className="font-semibold">Contact</dt><dd>{review.seller.name}</dd><dd>{review.seller.phone}</dd><dd>{review.seller.email}</dd></div>
                  <div><dt className="font-semibold">Selected preferences</dt><dd>Human callback: {review.selections.human_callback_requested ? 'Requested' : 'Not requested'}</dd><dd>Email reply: {review.selections.email_reply_requested ? 'Requested' : 'Not requested'}</dd></div>
                </dl>}
                {definition && <div className="space-y-2 text-sm text-slate-600"><p>Acknowledged: {definition.privacy_acknowledged}</p><p>{definition.human_callback_requested}</p><p>{definition.email_reply_requested}</p></div>}
                <p className="text-sm text-slate-600">Submitting asks Hilltop to review this property. Any purchase offer requires further review.</p>
                {!busy && <SellerChallenge key={challenge} siteKey={display.bot_site_key} inquiryId={inquiryId} onToken={onToken} />}
                <div className="flex justify-between gap-3">{!pending && <button type="button" className="flex items-center gap-1 px-3 py-3" onClick={() => { setToken(null); setStep(3); }}><ChevronLeft size={18} />Edit details</button>}
                  <button type="button" className={`${primary} ml-auto`} disabled={busy || !token || cooldown > 0} onClick={() => { void submit(); }}>{busy ? 'Confirming…' : cooldown ? `Retry in ${cooldown}s` : pending ? 'Retry same request' : 'Request an offer'}</button></div>
                <p className="text-xs text-slate-500">Unconfirmed requests are kept in this browser tab so you can retry without starting over.</p>
              </div>}
          </>}
      </section>
    </div>
  </main>;
}
