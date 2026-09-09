# Readiness review — September 8, 2026

The release fixes seller intake, operator access, and analysis persistence. PR #5 was merged with owner approval as `0009efa`, and its Vercel production deployment succeeded. The Supabase restoration and access-policy migration have also been applied with owner approval.

Review and deployment tracking: [PR #5](https://github.com/julysses/Wholesale-automation/pull/5). GitHub backend/frontend CI and the Vercel preview check passed for application commit `3db2469`.

## Fixed

- Public `/form/:formId` pages work independently of operator sign-in and runtime auth configuration.
- Form submissions enforce configured required fields, phone/email formats, valid choices and explicit checkbox consent. The API returns success only after the submission is saved. Database failures return a retryable error.
- Operational FastAPI routes validate a Supabase access token and require an approved profile. Health/config, public seller forms, and separately signed provider webhooks retain their intended access. Provider-key testing requires an administrator.
- All active frontend operational API callers attach the current access token. Failed requests throw an error rather than allowing a success toast.
- Persisted pending, denied, and suspended sessions cannot mount the dashboard or automatic scorer. Setup and user administration require an administrator. Auth cleanup cannot turn StrictMode initialization into a configuration error.
- User changes clear query data and selected lead/deal state; cancelled scoring ignores late responses.
- Database profile policies no longer recurse. Restrictive approval policies protect existing shared business tables; eight reporting/profile views now respect underlying row policies. Administrator RPCs check current approved status.
- Deal Analyzer saves into `deal_analyses` for Acquisitions visibility, updates the selected lead, releases its save button on failures, and calls the backend AI endpoint. AI failures produce errors without fabricated positive recommendations.
- Shared input/select controls generate IDs so their labels work with keyboards, screen readers and automated tests.
- Pages load on demand. The initial application bundle is substantially smaller than the original 1.54 MB bundle.
- Dependency audit findings were addressed, including replacing obsolete npm SheetJS with the maintained [official 0.20.3 package](https://docs.sheetjs.com/docs/getting-started/installation/nodejs/).

## Verification

- Backend regression suite, frontend regression suite, TypeScript/production build, dependency audit and lint-regression gate run locally; final counts are in `tasks/final-readiness.md`.
- Database migration tested in a rolled-back transaction: approved admin profile/lead access succeeds, pending accounts cannot read leads/buyers, own profile stays readable. Applied migration then independently checked with authenticated-role JWT claims.
- Supabase advisors no longer report security-definer view errors. Remaining warnings include older function search paths and disabled leaked-password protection; narrow guarded authorization helpers intentionally remain executable by authenticated users.
- Confirmed the production form configuration endpoint returns the Hilltop form after database restoration.
- The old production UI redirected seller-form visitors to login. Automated DOM tests verify the replacement route. Local browser visual inspection was blocked by the browser client (`ERR_BLOCKED_BY_CLIENT`); no successful visual QA claim is made.
- Tests mock external sends and AI calls. No real SMS, emails, calls, ad publishing or seller submissions were performed.

## Release / resume checklist

1. Completed: PR #5 merged and Vercel production deployment verified. Live health and Hilltop form configuration return 200; anonymous scoring-status access returns 401. Two Railway deployments succeeded; `practical-youthfulness - web` was still pending at handoff.
2. The new `20260908200130_approval_access_repair.sql` migration is already applied to project `dvzhzlipbwzzcliujzyz`. For a new environment, run all supplied migrations in filename order, including this one; the older `setup_all.sql` does not include subsequent migrations.
3. Use an approved operator account to verify sign-in, dashboard loading, imports, scoring and analysis saves on the deployed version. Confirm an incognito seller-form link stays on the form and anonymous operational APIs return 401.
4. Finish desktop/mobile visual QA and a controlled integration test of the messaging providers before calling the whole platform final.

## Remaining work, not claimed complete

- Existing lint debt: 181 errors and 5 warnings, mostly unused declarations and broad `any` types. `npm run lint` still reports these. `npm run lint:check` compares exact file/rule/message counts with `lint-baseline.json` and fails new findings. The baseline is explicit debt, not a clean lint certification.
- Persisted form submissions can still need operator recovery if background lead processing fails; a durable retry worker for this intake path is future work.
- Analyzer saves now share the Acquisitions table, but automatic lead-link prefill and reopening prior analyses for editing are still roadmap work. Updating the separate lead repair estimate can fail after the analysis saves; this is reported explicitly.
- Broad roadmap items in README (additional valuation providers, cross-device strategy preference, full integration coverage) were not represented as complete by this review.
