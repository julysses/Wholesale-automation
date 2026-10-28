# Acquisition review browser fixture

From `frontend`, run:

```sh
./node_modules/.bin/vite --config tests/browser/vite.config.ts
```

Open `http://127.0.0.1:5179/tests/browser/acquisition-review.html`.

This renders the real review component and stylesheet, while replacing only the API module with a synthetic, in-memory adapter. No user session, Supabase connection, environment file, provider or real mutation is used. The server binds localhost, has no API proxy, and fails on unhandled mock paths. Do not use this config for deployment or production acceptance. The normal Vite build still uses the normal entrypoint and API module.

Repeatable checks:

1. Select Hilltop local QA and open the proposal.
2. Verify address, exact revision, three cases and financial units; unknown equity must remain Unknown.
3. Select Approve amount. Recording stays disabled until the decision note, seven diligence notes and acknowledgment are supplied.
4. Record the synthetic decision; verify confirmation, approved queue status and revocation action.
5. Inspect a 375px mobile viewport and restore the normal viewport afterward.
6. Check browser console errors. Reloading discards all fixture decisions.

The fixture validates browser presentation and interaction only. Session/RLS, real API persistence, provider integration and production cutover require separate acceptance tests.

Inquiry recovery checks:

1. Select the fixture workspace and open Review hold. Verify credential guidance, exact timestamp, empty history and disabled approval.
2. Enter a correction note of at least 20 characters and an evidence reference, then acknowledge the specific hold.
3. Approve the synthetic cycle. Verify the recorded history, confirmation, disabled repeat approval and Awaiting worker count of one. No worker runs in this fixture.
4. Reload resets the synthetic hold. Component tests separately cover unknown responses, exact-request retries, stale gates, roles and exhausted recovery budgets.

Intake identity checks:

1. Open Seller intake identity review and select Review intake. Confirm seller assertions and missing fields remain distinct from canonical candidate evidence.
2. Select the synthetic property, choose Parcel document, enter a property evidence reference and a review note, and acknowledge the displayed evidence. Recording must remain disabled before these requirements are met.
3. Record the link, then verify the current-link indicator and history entry. Select Revoke prior link, document a correction, acknowledge it and record. Verify sequence two, no current valid link, and both historical decisions.
4. Component tests separately exercise repeat-inquiry seller evidence, lost replies with exact retries across queue refresh, stale hashes, operator restrictions and workspace switching. These synthetic actions never call a provider or database.

Qualification checks:

Open the synthetic intake and verify Current acquisition screening shows Incomplete with missing condition/timeline. Save assessment snapshot; verify matching-current confirmation, disabled redundant save and Version 1 history. Identity review changes refresh the screening and make the prior snapshot stale. This fixture provides display state only; the real qualification policy is covered by isolated PostgreSQL tests.

For the qualified-intake handoff fixture, append `?qualified=1` to `acquisition-review.html`. This seeds synthetic complete seller answers and a reviewed canonical link. Open the intake, choose Underwrite qualified intake, and save blank underwriting inputs: the fixture returns an incomplete scenario plus the automatic assessment snapshot. It has no provider/database transport and does not validate production calculations.

Campaign draft checks:

Select the local QA workspace, enter a campaign name and USD budget, and save. Verify a draft card with exact budget and unavailable observed spend. The adapter keeps synthetic campaign rows in memory and cannot publish or fund anything. The real component preserves uncertain requests in tab session storage; completed saves clear them. Reload resets the fixture database, so this fixture is not persistence/reconciliation acceptance. Component tests separately exercise lost responses, reload recovery, permission changes and tenant denial.

Campaign attribution and source snapshot checks:

Create a synthetic Facebook draft, open the fixture intake, and choose Review campaign attribution. Select the draft, enter an illustrative numeric ad-account ID, ownership evidence reference and review note, then acknowledge and record. Capture current attribution; verify one current snapshot and a disabled repeated-capture button. Revoke the campaign link with a correction reference/note and acknowledgment. Verify no current reviewed link, preserved Historical attribution, and disabled capture. The mock adapter stores all changes in memory and performs no database or provider action. These checks were rendered in the local browser on October 26; see the source-history screenshot in docs/acquisition-automation/evidence. They do not prove live account ownership, MFA/RLS or provider acceptance.


Property source checks (October 26): select the local workspace, expand Underwrite a property, and select 123 Fixture Lane. Open Property inquiry sources. The first page deliberately contains 20 excluded candidates and no eligible touches; More property sources must remain enabled. Continue to a separate reviewed repeat inquiry with historical campaign attribution, expand Association evidence, then refresh from the first page. The fixture exposes no source mutation or real transport. At 375px width, verify UUID wrapping, stacked navigation and no clipping. Evidence: `docs/acquisition-automation/evidence/2026-10-26-property-sources-mobile.jpg`. The existing proposal-review fixture remains separate; selected-property saved scenarios are empty.


Campaign cost checks: append `?costs=historical` (or `?costs=current`) to the fixture URL. Select the local workspace and View campaign costs. Set October 24–25, 2026, then Load cost coverage and expand daily evidence. Historical mode must show unavailable totals, a marked historical $125.50 day and a missing day. Current mode shows incomplete coverage with observed $125.50 and no complete total. Dates are account-calendar dates; native keyboard/date-picker actions commit React input state. This adapter is synthetic/in-memory and has no provider transport. Browser inspection on October 26 confirmed historical mode at 375px width without console errors.


Reviewed cost-entry fixture:

Run `./node_modules/.bin/vite --config tests/browser/cost-entry.vite.config.ts`, then open `/tests/browser/cost-entry.html`. Use only one fixture server at a time on port 5179. This dedicated adapter has canonical synthetic UUIDs, an in-memory ledger and no network/database/provider calls. Reload resets the ledger, so do not use reload as persistence acceptance; component and real-SQL tests cover that separately.

Choose Save then lose response, open entry and enter a past reporting date, partial USD cost, America/Chicago timezone, explicit observed timestamp, synthetic evidence reference and 64-character lowercase hash. Prepare, review the exact derived revision/account and acknowledge. After recording, verify one revision, locked input and exact retry. Retry must clear the lock without increasing the revision count. Then choose Confirmed rejection, prepare the next revision and record: verify no new revision, editable inputs, no retained preview and disabled save until re-preparation. October 26 browser QA completed this path with $125.50 on October 24 and inspected the final rejection at 375px; no console errors. Screenshot: `docs/acquisition-automation/evidence/2026-10-26-cost-entry-mobile.jpg`.

## Mail draft recovery fixture

Run `./node_modules/.bin/vite --config tests/browser/mail-templates.vite.config.ts` from frontend, then open `http://127.0.0.1:5181/tests/browser/mail-templates.html`.

The API alias is entirely synthetic: no network requests, credentials, database, approval or fulfillment. Ledger rows and pending requests survive reload in the same tab. A fresh tab provides a separate session. Use only synthetic text.

Verified October 28, 2026 in the in-app browser:
1. Save a named letter with `{{tracking_phone}}`; inspect ledger: 1 version.
2. Select “Save then lose response”, edit content, save; controls lock and ledger becomes 2.
3. Reload; exact-retry action and locked content survive. Retry and inspect: still 2 versions, version 2 confirmed.
4. Select version 1 and save; stale version is rejected without overwrite.
5. Select version 2, choose Postcard / Landing page; save stays disabled until `{{tracking_url}}` is present. Save then records version 3.
6. Template markup such as `<img src=x onerror=alert(1)>` displays as text in history. No script execution or console errors observed.

This is component/browser evidence, not live API/provider, full accessibility or all-device acceptance.

## Destination review recovery fixture

Run `./node_modules/.bin/vite --config tests/browser/mail-destinations.vite.config.ts` from frontend, then open `http://127.0.0.1:5182/tests/browser/mail-destinations.html`.

The adapter is entirely synthetic and never fetches a provider/API. A single synthetic approved destination seeds the tab-persistent ledger. Its 2099 expiry is test data, not an approved retention/verification policy. Role changes are test controls only; actual roles remain governed by SQL. A fresh tab starts independent data.

Verified October 28, 2026 in the in-app browser:
1. Open destinations and inspect the seeded row. Current state is version 1; fields stay locked until explicitly loading current details.
2. Load details, enter a synthetic review reason and check the evidence attestation. Select “Save then lose response” and record approval. Controls lock, exact retry appears and ledger count becomes 2.
3. Reload. Pending request/locked content survive; current state shows committed version 2. Retry and inspect ledger: still 2 reviews, with confirmed result.
4. Enter a withdrawal reason and withdraw. History remains intact, current state becomes withdrawn/version 3 and ledger count becomes 3.
5. Switch simulated role to Operator and refresh. Approval/edit controls remain unavailable and history remains inspectable. No console errors/warnings were recorded.

Reviewed a full-page screenshot at the browser's current viewport. This is not a comprehensive responsive/accessibility audit or live API/provider acceptance. The app-to-real-SQL tests separately cover authority, retry and history behavior.
