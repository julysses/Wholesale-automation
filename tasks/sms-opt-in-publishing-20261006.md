# SMS opt-in publishing checkpoint — October 6, 2026

User confirmed Hilltop Home Co. is a DBA of The Jays Dallas, LLC and authorized website changes for the opt-in process.

## Completed

- TheJaysDallas PR #3 merged, commit 506dd21b6e0c3337bfd2a4af5b48c5d6b63b144a. Public /sms instructions link to Hilltop's real offer form; footer/companies page states DBA relationship; SMS policies and terms match property inquiry updates. Preview verified at https://deploy-preview-3--thejaysdallas.netlify.app/sms.
- Jays Next.js updated to 16.3.8; lint/build/type checks pass, production audit zero. Development braces/fast-glob audit remains; no forced incompatible downgrade applied.
- HilltopHome PRs #4 and #5 merged. Optional unchecked consent identifies both entities and message scope, rates, frequency, STOP/HELP and no purchase condition; adjacent policy/terms links. Rendering version/text travels with submission; stale opted-in forms return 409. Actual source path validated (homepage and standalone page); unknown source remains null.
- Hilltop removed Meta pixel and server conversion delivery so form contact information/consent is not sent to advertising providers. Regression tests including no Meta request with configured credentials pass; production build/type/lint pass.
- Wholesale-automation PR #17 merged at baeb25f557ac86b2a41cd54f9a3fba4e9a0f017c. Receipt now stores server-owned choice, configured disclosure/hash/time/form identity. Frontend dependency audit repaired; checks passed.
- Wholesale-automation PR #18 (now merged; see verification below): it adds rendered disclosure matching (409 before save on stale/missing opted-in disclosure), direct CRM form metadata and client-reported source. 24 public-form tests, 96 frontend tests and build pass locally. The website-first deployment gate has now been satisfied.
- Supabase live hilltop-home-co SMS question label updated to the full matching DBA/program disclosure; required=false retained. No schema/permission changes.

## Production verification — October 6, 2026, 3:15 PM Central

- Netlify signed-in dashboard confirmed main auto-publishing enabled. Both sites finished publishing; no settings or DNS changes were necessary.
- https://thejaysdallas.com/sms live and visually verified. Hilltop /get-an-offer has exact DBA/program disclosure, optional checkbox initially unchecked, and adjacent privacy/terms/help links. Both sites' SMS privacy and terms URLs return 200.
- Wholesale PR #18 merged at fb39d6c0b4edf1c16600a9d57a49c0e12e87bcb4 after all checks passed. Vercel and all three Railway deployment statuses now success.
- Live Hilltop API rejected stale accepted disclosure with HTTP 409.
- Controlled live submission used Julio's authorized phone/email with SMS declined. HTTP 200 confirmed; receipt cf68ee58-fad5-4995-ad73-c269b06f8809 is processed and linked to lead 3d3ef68a-c05e-4529-8b12-66f38066e9f3. Database receipt preserves accepted=false, exact disclosure, SHA256, server timestamp, source /get-an-offer, rendered_disclosure_matches=true.
- Synthetic lead was then archived as dead, AI calling paused, both sequences off; its task marked done. No seller outreach enabled.
- Twilio Fix Campaign modal filled with corrected seller-inquiry description, four samples, actual public consent flow, and existing policy URLs. Not submitted: final correctness/vetting checkbox remains unchecked. Draft excludes internal employee alerts, unrelated marketing, lending and AI calls. Messaging flags links and phone=true, lending/age=false.

## Exact resume checkpoint

1. User personally agreed and submitted the corrected campaign. Refreshed Console confirms Campaign status In progress and under review. Corrected description, four samples, consent flow and policy links persisted. Console estimates 2-3 weeks; no carrier approval or delivery is claimed.
2. Carrier review is pending. No further submission is necessary now; do not repeatedly edit or recreate the campaign.
3. Complete native signed Twilio inbound STOP/reply and status callback integration; provider keys remain missing. Do not use Launch Control's differently signed endpoint.
4. Configure existing sender +14698049920/service, server-side credentials, and controlled delivery/STOP tests using Julio only after campaign approval. Positive consent acceptance and delivery remain to be tested; today's end-to-end test was declined SMS.
5. Internal owner SMS alerts need separate accurate opt-in coverage. AI-call consent, email/Retell/Facebook provider checks and isolated restore test remain open launch gates.

Proof: outputs/sms-opt-in-live.jpg, outputs/hilltop-consent-live.jpg, outputs/twilio-campaign-ready.jpg. Final screenshot of Twilio is an unsaved draft, not a completed submission.

Preserve unrelated untracked docs/deployment-vercel 2.md and tests/form-validation 2.mjs. Backend checkpoint branch codex/launch-runtime-checkpoint.

## Submission verified

User submitted final attestation personally. Initial page retained a stale Rejected label alongside the new review banner; after reload the explicit Campaign status changed to In progress. Proof saved to outputs/twilio-campaign-submitted.jpg. Do not interpret the old label as a second rejection.

## Sender association and remaining integration

Linked existing number +14698049920 (PNb952c10eb0350422ccd08b1d8c5ce738) to the campaign's Messaging Service MGaf5837f7a7cad183e8b38b1147728562. Verified number now appears in Sender Pool. No new number purchased, no message sent. Proof: outputs/twilio-sender-linked.jpg.

Service Integration currently defers inbound traffic to the sender webhook; delivery status callback is blank. Left these unchanged until native Twilio signature validation, durable inbound processing and status callback endpoints exist and pass tests. Code inspection confirms tools/sms_client.py dispatches directly from the number and does not yet provide a status callback or persist the Twilio Message SID. Its missing-credentials dry-run path marks a message sent; production must fail closed instead before enabling live automation. These are concrete implementation gates, not carrier-review blockers.

Next technical step: implement and test native Twilio callbacks and production fail-closed sending on the latest production branch, then wire server-side credentials and service callbacks. Do not treat this checkpoint branch as latest production source. Keep SMS launch blocked pending carrier approval and controlled delivery/STOP acceptance.
