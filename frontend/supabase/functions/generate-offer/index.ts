// Retired duplicate AI pricing path. The authenticated API accepts human-entered terms.
Deno.serve(() => new Response(JSON.stringify({
  error: 'offer_pricing_retired',
  message: 'Use the authenticated app to enter and approve offer terms. AI pricing is disabled.'
}), {status: 410, headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}}));
