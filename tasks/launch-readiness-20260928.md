# Launch readiness continuation — September 28, 2026

Working branch: `codex/hilltop-launch-hardening`; review: PR #9.
Decision: **blocked for live launch** until database connectivity and integration acceptance pass.

## Completed this session

- Pulled tracked branch successfully at `6cdcecd`; preserved existing untracked documentation.
- Rechecked Supabase project `dvzhzlipbwzzcliujzyz`: ACTIVE_HEALTHY in project inventory, but SQL, migration list, and security advisor queries time out. Postgres log query returned no rows; this does not establish database health or the root cause.
- Production `/api/health` returns 200; `/api/forms/hilltop-home-co` returns 404. The production build still masks database lookup failures as missing forms.
- Reran backend tests: 251 passed. Baseline frontend: 88 passed. Build, lint regression gate (157 existing findings), and npm audit (zero findings) passed.
- Added accurate public-form outage versus missing-form messages, a read-only retry button, 15-second config-fetch timeout, and request cleanup. All 91 frontend tests passed; updated build and lint regression gate passed. Commit `b539858` is pushed; GitHub backend/frontend checks and Vercel preview passed for this head.
- User initiated the Supabase restart. Dashboard and connector confirmed RESTARTING; the lifecycle API subsequently returned ACTIVE_HEALTHY, but the dashboard showed Unhealthy.
- Post-restart SQL failed twice with ECONNREFUSED to the database host on port 5432. At 2026-09-29 01:02 UTC, production form lookup still returned 404. Recovery is not established.
- Database observability could not load connection/disk/network metrics. Network restrictions page states all IP addresses can access the database; banned-IP retrieval failed with `Failed to fetch (api.supabase.com)` and directs the operator to support. No restrictions, passwords, compute sizes, or data were changed.

## Resume steps

1. Investigate the persistent post-restart database connection refusal with Supabase support. Network-ban status is unavailable. After recovery, verify SQL and migration/advisor access plus public form lookup. Do not replay migrations or recreate form records while connectivity is broken.
2. Reconcile current database policies/history against pending public-intake migration; use isolated acceptance before any rollout.
3. Trace the separate Netlify website intake into this CRM; verify contact number and optional SMS consent.
4. Finish durable submission recovery, operator role acceptance, owner assignment/alerts, and explicitly authorized provider delivery and STOP tests.
5. Review/release PR #9 only after remaining acceptance gates; verify the actual production deployment and intake afterward.

No live messages, calls, ad activation, schema changes, or deployment have been performed in this continuation. See `docs/hilltop-launch-hardening.md` for existing candidate fixes and `docs/hilltop-30-day-launch-plan.md` for the broader operating checklist.
