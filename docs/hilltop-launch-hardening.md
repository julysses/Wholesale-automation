# Hilltop launch hardening — September 28, 2026

Release decision: **candidate prepared; production launch remains blocked**.

## Production diagnosis

Vercel runtime logs for the current production deployment show Supabase REST HTTP 522 responses to `lead_form_configs` queries. Both direct database inspection and migration-history inspection timed out. The public application caught those exceptions and returned HTTP 404 after approximately 40 seconds. This establishes an upstream connectivity failure at the time of inspection, not a missing form record. The provider's ACTIVE_HEALTHY label did not establish query availability.

Resolve database connectivity through Supabase health/logs/support and confirm queries before repairing or recreating form configuration. Do not recreate records or replay migrations to treat this outage.

## Release candidate changes

- Public form reads and submissions share one lookup. Slugs query the slug column; UUIDs query the ID column. Database failures return 503 with Retry-After; only a successful empty lookup returns 404. This avoids the second doomed database request and the invalid UUID lookup for ordinary slugs.
- Includes the pending Facebook changes from PR #8: native Facebook leads use the immediate owner-alert path and recognize affirmative SMS consent. PR #8 remains open; this candidate incorporates its code rather than claiming it is deployed.
- Saves a deterministic in-app admin notification before attempting SMS, independent of seller score and SMS delivery hours. The application notification uses the existing `app_notifications` schema and displays outcome information in its body on fetch/reload.
- Blocks seller SMS when consent is absent/negative, suppression lookup fails, the current lead is missing or DNC is unknown, another exact-phone lead is suppressed, or a recent same-phone/property inquiry exists.
- Records accepted, failed-or-blocked, dry-run, missing configuration and unknown delivery results. Provider acceptance is not marked as delivery confirmation.
- A deterministic notification receipt prevents repeat sends on retries. Interrupted attempts remain unresolved and require operator reconciliation; no automatic retry of possibly delivered messages is added.
- Adds the missing Twilio SDK to deployment requirements, pinned to the version exercised locally, with a test that imports the real package and mocks its external call.

## Validation

Backend: **251 tests passed**, including outage-vs-missing-form behavior, consent/suppression failures, notification persistence, interrupted result writes, retry protection and the packaged Twilio dispatch contract. Frontend: 88 tests passed; typecheck/production build passed; lint regression gate passed with 157 existing findings; npm audit reported zero known vulnerabilities. Existing large-bundle and Python deprecation warnings remain. Tests use provider mocks and do not establish live delivery.

## Remaining production gates

1. Restore Supabase query connectivity, confirm active public form, reconcile migration histories and validate anonymous-write restrictions in isolated staging.
2. Identify the separate Netlify website source and trace `/api/get-offer` into the actual backend. Website number and mandatory-SMS-consent behavior remain unchanged by this repository patch.
3. Verify SMS sender approval/configuration, live authorized receipt, STOP synchronization across leads/buyers, phone normalization, and an independent after-hours owner alert channel. Telnyx/MessageBird SDK compatibility and packaging are not certified; use only an explicitly verified provider.
4. Rehearse durable submission processing, stalled jobs, exact-role access, and recovery. The existing web submission processor is still a serverless background task; the notification receipt is at-most-once attempt protection, not an always-running worker or automatic recovery system.
5. Confirm operational ownership. A saved admin notification does not assign a task or guarantee the operator is online; assignment, escalation and staffing remain required.
6. Review the candidate, stage it with isolated data, run selected provider acceptance, then release and repeat production checks before ads.

## Recovery rules

For unresolved or unknown outcomes, inspect the notification, saved lead/submission, logs and provider history. Establish whether a message was accepted before taking a manual next action. Do not delete the deterministic notification to force a resend. Failed notification persistence before a send blocks that send; the saved lead/submission and production error logs remain the recovery sources.

## Handoff

Code branch: `codex/hilltop-launch-hardening`. Full operating checklist: `docs/hilltop-30-day-launch-plan.md`. No database migration, production deployment, live message/call or paid ad activation was performed. Existing untracked `docs/deployment-vercel 2.md` was left untouched.
