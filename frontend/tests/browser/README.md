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
