import { useEffect, useRef, useState } from 'react';

type Widget = { render: (element: HTMLElement, options: Record<string, unknown>) => string; remove: (id: string) => void };
declare global { interface Window { turnstile?: Widget } }
const SOURCE = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
let loading: Promise<Widget> | null = null;
function loadWidget(): Promise<Widget> {
  if (window.turnstile) return Promise.resolve(window.turnstile);
  if (loading) return loading;
  loading = new Promise<Widget>((resolve, reject) => {
    const script = document.createElement('script');
    const timer = window.setTimeout(fail, 12000);
    function fail() { window.clearTimeout(timer); script.remove(); loading = null; reject(new Error('Verification unavailable')); }
    script.src = SOURCE; script.async = true; script.defer = true;
    script.onload = () => { window.clearTimeout(timer); if (window.turnstile) resolve(window.turnstile); else fail(); };
    script.onerror = fail;
    document.head.appendChild(script);
  });
  return loading;
}

export function SellerChallenge({ siteKey, inquiryId, onToken }: { siteKey: string; inquiryId: string; onToken: (value: string | null) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true; let widget: string | undefined; let api: Widget | undefined;
    onToken(null);
    void loadWidget().then(value => {
      if (!active || !container.current) return;
      api = value;
      const unavailable = () => { if (active) { onToken(null); setError(true); } };
      widget = value.render(container.current, {
        sitekey: siteKey, action: 'acquisition_offer', cData: inquiryId, theme: 'light',
        callback: (token: string) => { if (active) { setError(false); onToken(token); } },
        'expired-callback': unavailable, 'timeout-callback': unavailable, 'error-callback': unavailable,
        'unsupported-callback': unavailable,
      });
    }).catch(() => { if (active) setError(true); });
    return () => { active = false; if (widget && api) api.remove(widget); };
  }, [siteKey, inquiryId, attempt, onToken]);
  return <div className="space-y-2"><div ref={container} aria-label="Verify your request" />
    {error && <div role="alert" className="text-sm text-amber-900">Verification needs another try. Your details are unchanged.
      <button type="button" className="ml-2 underline" onClick={() => { setError(false); setAttempt(value => value + 1); }}>Retry verification</button>
    </div>}
  </div>;
}
