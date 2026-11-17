"use client";

import { useEffect, useRef, useState } from "react";

type Turnstile = {
  render: (element: HTMLElement, options: {
    sitekey: string;
    action: string;
    size: "flexible";
    "response-field": false;
    callback: (token: string) => void;
    "expired-callback": () => void;
    "error-callback": () => void;
  }) => string;
  remove: (widgetId: string) => void;
};

const SOURCE = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
let pendingScript: Promise<Turnstile> | undefined;

function loadTurnstile() {
  const browser = window as Window & { turnstile?: Turnstile };
  if (browser.turnstile) return Promise.resolve(browser.turnstile);

  pendingScript ??= new Promise<Turnstile>((resolve, reject) => {
    const script = document.createElement("script");
    const timer = window.setTimeout(fail, 10_000);

    function fail() {
      window.clearTimeout(timer);
      script.remove();
      pendingScript = undefined;
      reject(new Error("Verification script unavailable"));
    }

    script.src = SOURCE;
    script.async = true;
    script.onerror = fail;
    script.onload = () => {
      if (!browser.turnstile) return fail();
      window.clearTimeout(timer);
      resolve(browser.turnstile);
    };
    document.head.appendChild(script);
  });
  return pendingScript;
}

export function WebsiteChallenge({ siteKey, action, onToken }: {
  siteKey: string;
  action: string;
  onToken: (token: string | null) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let disposed = false;
    let removeWidget: (() => void) | undefined;
    const fail = () => {
      if (!disposed) {
        onToken(null);
        setFailed(true);
      }
    };
    loadTurnstile().then(turnstile => {
      if (disposed || !container.current) return;
      const id = turnstile.render(container.current, {
        sitekey: siteKey,
        action,
        size: "flexible",
        "response-field": false,
        callback: token => {
          if (!disposed) {
            setFailed(false);
            onToken(token);
          }
        },
        "expired-callback": () => { if (!disposed) onToken(null); },
        "error-callback": fail,
      });
      removeWidget = () => turnstile.remove(id);
    }).catch(fail);
    return () => {
      disposed = true;
      removeWidget?.();
    };
  }, [siteKey, action, attempt, onToken]);

  return (
    <div>
      <div ref={container} />
      {failed && <div className="text-sm" role="status">
        Verification is temporarily unavailable.{" "}
        <button type="button" className="underline" onClick={() => {
          setFailed(false);
          setAttempt(value => value + 1);
        }}>Reload verification</button>
      </div>}
    </div>
  );
}
