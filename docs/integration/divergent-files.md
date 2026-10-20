# Divergent overlap: all 48 files

Pinned collection `8bec6d825071993d59bc623b346046c3f249fba2`; production `19c117ad7a8ab10656bf116a2a6835508f7f1f01`. These are divergent blobs, not a claim that Git would report 48 textual merge conflicts. See the main assessment for bundle dependencies and future regression gates.

| File | Disposition | Requirement |
|---|---|---|
| `.github/workflows/ci.yml` | RECONCILE | Keep production credential-routing and SMS contention jobs; ensure collection offer/lot/valuation suites remain wired. |
| `.gitignore` | PRESERVE_PRODUCTION | Retain production local-artifact exclusions; inspect tracked node_modules symlink separately. |
| `docs/START-HERE-NEXT-CHAT.md` | PRESERVE_PRODUCTION | Use production October 19 pause as controlling; preserve collection history as historical evidence only. |
| `docs/retell-sms-scheduler.md` | PRESERVE_PRODUCTION | Keep production installation/transport documentation and pause; do not install or activate either scheduler. |
| `frontend/src/App.tsx` | PRESERVE_PRODUCTION | Retain production Layout route and DailyLists component admin guard; verify newly added feature routes independently. |
| `frontend/src/components/WorkflowGuide.tsx` | RECONCILE | Reconcile production evidence-based onboarding wording with collection human-price/approval boundaries. |
| `frontend/src/components/lists/ForeclosureActions.tsx` | PRESERVE_PRODUCTION | Keep production inline identity review, query invalidation and stale-error protection. |
| `frontend/src/components/lists/ReviewControl.tsx` | PRESERVE_PRODUCTION | Keep production tax-snapshot warnings, missing-situs handling and zero-address rejection. |
| `frontend/src/hooks/useNotifications.ts` | PRESERVE_PRODUCTION | Keep production refresh/error/race/deduplication/read-state behavior with NotificationPanel and lead deep links; assess DELETE refresh semantics. |
| `frontend/src/hooks/useWorkflowStep.ts` | RECONCILE | Reconcile production setup/import guidance with collection guarded calling and manual-offer workflow descriptions. |
| `frontend/src/pages/DailyLists.tsx` | RECONCILE | Reconcile collection lot controls with production source-filtered reviews, property review actions and PropStream sections. |
| `frontend/src/pages/Leads.tsx` | RECONCILE | Retain production deep links, keyed drawers and server CSV reconciliation; port collection human contract-price entry, date validation and action label. |
| `frontend/supabase/migrations/20261015023121_weekly_tax_monitoring.sql` | RECONCILE | Same migration ID, different body: preserve production no-delete monitoring; audit deployed definition/history before forward reconciliation. |
| `frontend/tests/daily-list-identity.test.tsx` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `frontend/tests/foreclosure-actions.test.tsx` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `frontend/tests/notifications.test.tsx` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `pipeline/collectors/deliver.mjs` | PRESERVE_PRODUCTION | Keep production endpoint/key-bound journal and per-project receipt filename; reject legacy/mismatched journals. |
| `pipeline/collectors/deliver_keychain.py` | PRESERVE_PRODUCTION | Keep production explicit environment/source credential scoping and rehearsal default; no invocation or keychain access. |
| `pipeline/collectors/foreclosure_batch.mjs` | PRESERVE_PRODUCTION | Keep production exact trustee-reference formats and conflict-aware suffix matching; never infer identity from OCR repair. |
| `pipeline/collectors/foreclosure_batch.test.mjs` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `pipeline/collectors/tax_roll.py` | PRESERVE_PRODUCTION | Keep production zero-filled/missing situs detection and raw evidence preservation. |
| `pipeline/integration/ingress-postgres.ts` | RECONCILE | Reconcile collection offer/lot/valuation coverage with production onboarding/auth/schema fixtures; retain both feature suites. |
| `pipeline/tests/collector-delivery.test.mjs` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `pipeline/tests/edge-deno.ts` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `pipeline/tests/foreclosure-batches.test.mjs` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `pipeline/tests/reviewed-identity.test.mjs` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `pipeline/tests/test_keychain_delivery.py` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `pipeline/tests/test_tax_roll.py` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `tests/test_daily_list_launch_guards.py` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `tests/test_dialer_export.py` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `tests/test_list_identity_api.py` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `tests/test_retell_form_sms.py` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `tests/test_retell_reply_routing.py` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `tests/test_retell_sms.py` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `tests/test_scoring_admin_api.py` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `tests/test_trace_operations_api.py` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `tests/test_twilio_integration.py` | RECONCILE_COVERAGE | Preserve production cases plus collection-only invariants; do not choose an entire branch test file merely to make CI pass. |
| `tools/retell_form_sms.py` | PRESERVE_PRODUCTION | Keep production transport ownership, exact job scope, contact-window/expiry, configured version and no route fallback. |
| `tools/retell_reply_routing.py` | PRESERVE_PRODUCTION | Keep production shared control classifier and native-only redirect ownership. |
| `tools/retell_sms.py` | PRESERVE_PRODUCTION | Keep production API-chat receipt routing, exact saved-chat fallback and wrong-number opt-out. |
| `tools/sms_client.py` | PRESERVE_PRODUCTION | Keep production explicit accepted/failed/blocked/unknown outcomes and confirmed-suppression separation; preserve shared receipt helper. |
| `web/api/__init__.py` | RECONCILE | Reconcile collection human-price/draft-only offer and outreach contracts with production import fields and confirmed-update checks; preserve both. |
| `web/api/lead_forms_api.py` | PRESERVE_PRODUCTION | Keep production owner-alert claim before queueing, schedule_unconfirmed handling, no fallback and explicit SMS outcomes. |
| `web/api/list_pipeline_api.py` | RECONCILE | Add collection lot routes/models to production filtered snapshot and zero-situs rejection; pair with SQL and role checks. |
| `web/api/nurture_api.py` | PRESERVE_PRODUCTION | Keep production scoped job/turn workers, recovery and inspect endpoints with secret and disabled gates; do not invoke. |
| `web/api/twilio_webhooks.py` | PRESERVE_PRODUCTION | Keep production atomic receipt-first flow, app transport sync, owner email and app-owned reply suppression of native redirect. |
| `web/api/webhooks.py` | RECONCILE | Reconcile collection call follow-up/opt-out task handling and human-price restrictions into production; do not replace webhook module. |
| `web/app.py` | RECONCILE | Retain production registrations; add offer_review and land_valuation routers only with their full dependency bundles. |
