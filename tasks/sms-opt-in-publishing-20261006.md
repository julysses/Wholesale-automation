# SMS opt-in publishing checkpoint — October 6, 2026

User confirmed Hilltop Home Co. is a DBA of The Jays Dallas, LLC and authorized website changes for the opt-in process.

## Completed

- TheJaysDallas PR #3 merged, commit 506dd21b6e0c3337bfd2a4af5b48c5d6b63b144a. Public /sms instructions link to Hilltop's real offer form; footer/companies page states DBA relationship; SMS policies and terms match property inquiry updates. Preview verified at https://deploy-preview-3--thejaysdallas.netlify.app/sms.
- Jays Next.js updated to 16.3.8; lint/build/type checks pass, production audit zero. Development braces/fast-glob audit remains; no forced incompatible downgrade applied.
- HilltopHome PRs #4 and #5 merged. Optional unchecked consent identifies both entities and message scope, rates, frequency, STOP/HELP and no purchase condition; adjacent policy/terms links. Rendering version/text travels with submission; stale opted-in forms return 409. Actual source path validated (homepage and standalone page); unknown source remains null.
- Hilltop removed Meta pixel and server conversion delivery so form contact information/consent is not sent to advertising providers. Regression tests including no Meta request with configured credentials pass; production build/type/lint pass.
- Wholesale-automation PR #17 merged at baeb25f557ac86b2a41cd54f9a3fba4e9a0f017c. Receipt now stores server-owned choice, configured disclosure/hash/time/form identity. Frontend dependency audit repaired; checks passed.
- Wholesale-automation PR #18 remains OPEN: it adds rendered disclosure matching (409 before save on stale/missing opted-in disclosure), direct CRM form metadata and client-reported source. 24 public-form tests, 96 frontend tests and build pass locally. Hold deployment until Hilltop's form changes are live to avoid blocking old accepted-consent submissions.
- Supabase live hilltop-home-co SMS question label updated to the full matching DBA/program disclosure; required=false retained. No schema/permission changes.

## Publishing blocker / exact resume point

The Netlify preview works, but the production domains still show older content: thejaysdallas.com/sms returned 404 and Hilltop form had the old label after Git merges. No production commit status was posted for either website merge. Need signed-in Netlify to inspect production branch, build/publish settings and queue. Do not assume the site was published merely because a PR merged.

Netlify login tab is open through GitHub and awaiting user sign-in. Browser tab 1348645356 (Chrome Julio). User was asked via async question to sign in. The Twilio campaign was not edited/submitted, no new credentials transferred, no fees accepted, no SMS sent. Corrected pages must be live before resubmission.

## Resume order

1. User signs in to Netlify; inspect thejaysdallas and hilltophome project production settings. Publish latest merged commits without changing domains/email DNS.
2. Browser-check /sms, its offer CTA, both policy links, and optional unchecked Hilltop consent on homepage and /get-an-offer. Save live screenshot proof.
3. Check PR #18 CI and merge/release after website publication; verify actual production deployment. Controlled submission using Julio contacts only; verify durable evidence, then archive fixture.
4. Review corrected Twilio campaign scope. Original rejected campaign was internal management alerts; proposed seller property inquiry campaign must not silently cover internal alerts, buyer blasts, unrelated marketing or AI calls. If owner SMS alerts are included, document a separate real employee opt-in mechanism and reflect it accurately in registration.
5. Complete native Twilio signed inbound STOP/reply and delivery callback integration; keys remain missing. Do not point number to Launch Control's differently signed endpoint.
6. Prepare final Twilio form, verify re-vetting fee, and request approval for the concrete correctness attestation/fee immediately before submitting. Carrier approval and controlled delivery tests remain open gates.

Local repositories: work/the-jays-dallas (codex/sms-opt-in), work/hilltop-home (codex/sms-consent-evidence); backend implementation branch codex/twilio-consent-records. Preserve unrelated untracked docs/deployment-vercel 2.md and tests/form-validation 2.mjs.
