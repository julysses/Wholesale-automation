// Retired duplicate: the app uses the authenticated Python draft endpoint.
export function handler(): Response {
  return new Response(JSON.stringify({
    error: 'outreach_writer_retired',
    message: 'Use the authenticated app to prepare fixed outreach drafts for human review. No message was generated or sent.'
  }), {status: 410, headers: {'Content-Type': 'application/json', 'Cache-Control': 'no-store'}});
}
if (import.meta.main) Deno.serve(handler);
