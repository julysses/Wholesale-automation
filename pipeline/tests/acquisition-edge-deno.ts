// Execute the legacy handler with only its external imports replaced by spies.
// Network permission is absent; no Supabase SDK, provider or deployment is used.
Deno.test('legacy Facebook edge handler and direct SMS cannot bypass acquisition hold', async () => {
  const path = new URL('../../frontend/supabase/functions/fb-lead-intake/index.ts', import.meta.url);
  const original = await Deno.readTextFile(path);
  const imports = original.match(/^import .*;$/gm) || [];
  if (imports.length !== 2) throw new Error('Review new Edge dependencies before updating this test');
  const source = `
let captured: (req: Request) => Promise<Response>;
function serve(handler: (req: Request) => Promise<Response>) { captured = handler; }
function createClient(...args: unknown[]): never { throw new Error('No database call allowed'); }
${original.replace(/^import .*;$/gm, '')}
export { captured as handler, sendSMS };
`;
  const previous = Deno.env.get('ACQUISITION_ENABLED');
  const originalFetch = globalThis.fetch;
  let fetches = 0;
  globalThis.fetch = () => { fetches++; throw new Error('No provider request allowed'); };
  try {
    Deno.env.set('ACQUISITION_ENABLED', 'true');
    const module = await import('data:application/typescript,' + encodeURIComponent(source));
    const response = await module.handler(new Request('https://fixture.invalid', {
      method: 'POST', body: JSON.stringify({ phone: '+12145550101', consent: true }),
    }));
    if (response.status !== 409 || (await response.json()).error !== 'acquisition_execution_not_authorized') {
      throw new Error('Expected acquisition hold before database access');
    }
    if (await module.sendSMS('+12145550101', 'Synthetic only') !== false || fetches !== 0) {
      throw new Error('Direct SMS must remain blocked');
    }
  } finally {
    globalThis.fetch = originalFetch;
    if (previous === undefined) Deno.env.delete('ACQUISITION_ENABLED');
    else Deno.env.set('ACQUISITION_ENABLED', previous);
  }
});
