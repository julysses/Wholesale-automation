# HANDOFF — read this first (updated 2026-11-26 by Claude)

Written so any agent (GPT/Codex or Claude) can resume without prior chat. Keep this file current: append a dated entry to "Progress log" after every meaningful step, and update "Next actions".

## 0. Critical orientation (a previous review got this wrong)

- This branch `claude/sharp-pasteur-jsp5w4` and the default branch `claude/ai-wholesaling-agency-KkDF1` are **stale** (last real work Oct 18). Do NOT plan from their `tasks/todo.md`, `docs/final-readiness-review.md` or from `docs/launch-completion-roadmap-20261126.md` without reading the correction in section 3.
- Real development continued on `codex/*` branches through **Nov 24, 2026**. Two divergent lines (common ancestor `c8673c1`, Oct 23):

| Line | Tip | Date | Ahead of default | What it holds |
|---|---|---|---|---|
| Acquisition / inbound | `origin/codex/inbound-next-milestone` `628fc02` | Nov 24 | 435 | Acquisition automation, disposition/buyer profiles, inbound AI (Retell) prep, direct-mail prep |
| Leads workflow / Facebook | `origin/codex/facebook-attribution-resolution` `e88a7c6` (based on `codex/wholesaleos-leads-workflow` `77e257f`, also `codex/website-turnstile` `1b784b9`) | Nov 24 | 130 | Mobile lead intake, follow-up queue, paid Hilltop lead reconciliation, Facebook attribution resolution |

- Other recent tips: `codex/hilltop-housing-form-consent` (Nov 17), `launch/phase-a` (Nov 12), `codex/website-spam-investigation-20261108`.
- Production on Vercel (project `prj_ZRURRXQ1GbBiIUBtmGFiYZdVMNgd`, team `team_XZeRcNxzGjDXsr7Z2AqwhfAe`) is **manually deployed**; deployment records carry no git SHA. Latest production deployment `dpl_CTWtVLLrUbp8cq3pqWjKyZYza8yw` (~Nov 21). **Which commit/line is live is unknown** — determine it (Vercel deployment file listing, `/api/health`, or ask owner) before any release.

## 1. Business state (from repo checkpoints; verify live)

- Owner (Julio) confirmed on Nov 24 that **Facebook ads have launched** and said proceed to the next step. That advances development; it does **not** certify open gates and does **not** activate inbound routing or outbound contact.
- Active milestone: **inbound AI preparation (Retell inbound agent)**, then **direct-mail preparation**. Resume file: `config/acquisition/inbound/README.md` on `628fc02`.
- Facebook residual work (branch `codex/facebook-attribution-resolution`, `docs/facebook-release/PROGRESS.md`): registered ad→campaign/creative resolution built; review-only reconciliation planner built (72 targeted tests pass). Remaining: authoritative Meta evidence, mapping registration, atomic audited application, integration acceptance, hosted launch gates. The existing production inquiry is NOT repaired.
- Earlier verified (Oct): auth/RLS, scoring backlog, intake references, SendGrid, Twilio restricted SMS, deal pipeline, QA-excluded reporting. See `tasks/final-launch-verification-20261008.md`, `tasks/production-acceptance-20261007.md`, `docs/facebook-release/LAUNCH-2026-10-23.md`.

## 2. Hard rules (do not violate; derived from owner instructions in repo checkpoints)

1. No production migration, deploy, provider POST, live SMS/email/call, paid generation, schedule activation, or ad change without **explicit owner authorization for that exact action**. Authorization does not carry over from a checkpoint or the overall goal.
2. Keep SMS schedulers, Retell cron jobs, Vercel outbound cron, collection schedules, calling/nurture, and acquisition inbound flags **disabled** unless the owner says otherwise.
3. Never replay old leads/turns; no bulk repair. Preserve held work. Do not apply migrations by directory-wide push or history repair; named migration only, bounded timeouts.
4. Never put real seller contact in tests; use labeled fixtures; QA records are reversibly excluded from reporting, not deleted.
5. Never log or capture credentials. Do not claim "production ready"/"launch certified" while any gate is open. Cumulative test spend cap observed: $5 (about $0.02 used as of Oct 19).
6. Pull/fetch before editing; re-inspect after sync. Local tests must force SQLite/disposable DB (never the developer `.env`). Python 3.11/3.12 per `runtime.txt`; sandbox here has 3.13.
7. Do not release the county integration as part of the Facebook launch. Spanish stays disabled pending bilingual acceptance.

## 3. Correction to `docs/launch-completion-roadmap-20261126.md`

That roadmap was built from the stale default branch. Treat as invalid: the "Retell deferred to v1.1" scope cut (Retell SMS pilot and inbound AI are active work on the real branches — **owner must re-confirm scope**), Phase 0's assumption that the `codex/twilio-live-integration` lineage is current, and "Facebook v1 form" items already superseded by `docs/facebook-release/`. Still valid in spirit: human acceptance gates (STOP, unsubscribe, restore rehearsal, failure alerts), business decisions (title partner, offer authority, ad cap, after-hours, buyer roster, legal, earnest money), rehearsal and go/no-go.

## 4. Next actions (ordered)

- [x] **N1 Identify live code — DONE 2026-11-26.** Production `dpl_CTWtVLLrUbp8cq3pqWjKyZYza8yw` (CLI deploy ~Nov 21, READY, no alias list) matches `origin/codex/wholesaleos-leads-workflow` @ `77e257f`: 508 of 509 deployed files are content-identical (sha1 of raw file == Vercel uid); the single differing file is `frontend/tests/lead-deep-link.test.tsx` (test only). Method: Vercel `list_deployment_files` uids are sha1 of raw content; compare with `git cat-file blob`. Versus this branch, only `web/api/webhooks.py` (attribution wiring), `docs`, and the new reconcile code/migration are undeployed. Original task text: Determine commit behind production (`dpl_CTWtVLLrUbp8cq3pqWjKyZYza8yw`) by comparing deployed file listing / health output to the two tips. Record result here. (Read-only.)
- [ ] **N2 Choose integration strategy** with owner: which line is the release trunk; plan a merge/rebase of the two lines (`628fc02` vs `e88a7c6`) into one reviewed branch, then retire stale default branch (and only then remove the `vercel.json` `git.deploymentEnabled` guard). Do not merge into default without owner approval.
- [~] **N3 Facebook attribution** — owner chose this line first (2026-11-26). DONE locally: `tools/facebook_attribution.apply_reconciliation`, migration `frontend/supabase/migrations/20261126000000_facebook_attribution_reconciliation.sql` (NOT applied anywhere), SQL proof `tests/sql/facebook_attribution_reconciliation.sql` (passed on a disposable local Postgres 16), 18 attribution tests, full backend suite 1187 passed/10 skipped. REMAINING: (a) owner-authorized production steps — fetch authoritative Meta lineage for the existing inquiry, register campaign/creative mappings, apply the migration (named migration only, bounded timeouts, backup point first), then call `plan_reconciliation` -> review -> `apply_reconciliation`; (b) wire an operator/admin entry point only if owner wants one (currently library + RPC only); (c) hosted acceptance with fresh controlled Meta lead; (d) frontend tests/build re-run (not run this session).
- [ ] **N4 Inbound AI prep** (branch `codex/inbound-next-milestone`): per `config/acquisition/inbound/README.md` "Resume in this package": verify the five tool contracts against a reviewed provider config; identify inbound number/agent/version and human handoff destination; prepare synthetic audio cases (identification, interruption, saved-state recovery, opt-out). No paid simulation or test call without authorization.
- [ ] **N5 Direct-mail prep**: resume from `docs/acquisition-automation/POSTAL-AND-BATCH-IMPLEMENTATION.md` (address eligibility, suppression, budget/cadence reservations before vendor/proofs). No purchase or dispatch.
- [ ] **N6 Human/provider gates** (owner hands): 0100 STOP/refusal, secondary-mailbox unsubscribe, restore rehearsal (DB/Auth/Storage/Edge), independent failure-alert receipt, handset confirmations, ambiguous-inquiry classification.
- [ ] **N7 Business decision sheet** (owner): title partner, offer authority, ad cap, after-hours coverage, buyer roster, legal templates, earnest-money process, rehearsal staffing, go/no-go.
- [ ] **N8 Rehearsal and go/no-go**, then staged removal of recipient restrictions (email → SMS → ads).

## 5. How to work

- Reproduce tests (from repo root, per `docs/facebook-release/PROGRESS.md`): `.venv/bin/python scripts/run_offline_tests.py .venv/bin/python -m pytest tests`; `... npm --prefix pipeline test`; `... npm --prefix frontend test -- --maxWorkers=2`; `... npm --prefix frontend run build`. These exist on the codex branches, not on this stale branch.
- Use `git worktree add ../wt-<name> origin/<branch>` to inspect a tip without disturbing this checkout.
- Large evidence files: `tasks/final-launch-verification-20261008.md` (~420 lines), `docs/START-HERE-NEXT-CHAT.md` (on codex branches, ~38KB, newest sections first).
- Update `tasks/todo.md` header pointer and this file at every checkpoint; commit to the working branch; never force-push.

## 6. Open owner questions (do not re-ask once answered)

1. ANSWERED 2026-11-26: Retell outbound calling/nurture deferred; inbound AI prep and SMS pilot remain in scope.
2. Which line is the release trunk (acquisition `628fc02` vs Facebook/leads `e88a7c6`), and may they be merged?
3. Which commit is production running?
4. Business decisions in N7.

## 7. Progress log

- 2026-11-26 Claude (6): Owner reported a red CI email (Frontend job). Root cause: run 986 on stale base code failed `npm audit` (vite/zod vulns); runs 987-990 on merged code pass. Full tool-driven code review written to `docs/code-review-20261126.md` (findings H1-H3, M1-M5, L1-L6, streamlining plan, CI additions). No code changed by the review. Owner said the review comes BEFORE the build; next the owner decides which review items to implement. Frontend tsc/eslint cannot run in the cloud sandbox (npm 403 on @typescript-eslint/utils 8.57.1) - rely on CI.

- 2026-11-26 Claude (5): Owner chose to get Meta lineage via computer use in their logged-in Ads Manager. `list_computer_folders` returned no folders and no `cannot_be_used` entries, so no user machine can be attached from this cloud session yet. Needed: owner adds a folder in the Claude desktop app (Settings > Claude Code > Remote Control) with that computer online, then ask the agent to `request_computer_folder`; OR run a desktop Claude session on the computer; OR paste IDs manually. Needed data: for each live campaign/ad set/ad: campaign id+name, ad id+creative name; and which ad produced each of the 7 leads (Meta Leads Center / form lead list `leadgen_id` -> ad). Leadgen ids to map: 2411126796296108, 1152024113869131, 1449644569971233, 897526946717404 (form 1548364970390755); 1018082827249001, 2632349200538064, 1807598620358246 (form 2089492558416792). Read-only in Ads Manager; do not change ads, budgets or permissions.

- 2026-11-26 Claude (4): **P1 read-only production inspection DONE** (Supabase project `dvzhzlipbwzzcliujzyz`, SELECT only, no PII read). Findings: migration history ends at `20261023221455` (Facebook receipts migration applied as `20261020192531`); reconcile function NOT present; `audit_logs` exists. `facebook_lead_submissions` = 7; leads with source `facebook_lead_ad` = 9 (2 are Oct 7 QA, reversibly excluded, no receipt); **0 of 9 attributed; `ad_campaigns` = 0 and `ad_creatives` = 0 (nothing registered)**. Seven real native inquiries: forms `1548364970390755` (4 leads, Nov 17) and `2089492558416792` (3 leads: Nov 17, 18, 21); lead ids start f41cbe64, f5806fac, c2f005d4, 4a6714dd, 6bd37180, 735327bf, 76679375. **P2 blocked from the Claude sandbox**: `graph.facebook.com` is unreachable (proxy, HTTP 000) so Graph lookups cannot run here, and Meta tokens were not read. Next: owner supplies campaign/ad IDs from Ads Manager OR a Graph lookup runs where Meta is reachable (owner machine or deployed app with a reviewed read-only endpoint). Then P3 register mappings, P4 migration, P5 deploy, P6 reconcile (all need exact-action authorization).

- 2026-11-26 Claude (3): Live code identified (see N1). Facebook attribution wiring (`web/api/webhooks.py` change from e88a7c6) and the reconciliation migration are NOT yet live. Next: owner-authorized production steps for attribution (see N3). No production change made yet.

- 2026-11-26 Claude (2): Owner answers: continue Facebook attribution first; Retell scope = defer OUTBOUND only (inbound AI prep + SMS pilot stay in scope). Merged `origin/codex/facebook-attribution-resolution` (e88a7c6) into this branch `claude/sharp-pasteur-jsp5w4` so it is now the working trunk for the Facebook line (push only to this branch). Built audited reconciliation applier + migration + SQL proof (see N3). Test env: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`; run `.venv/bin/python scripts/run_offline_tests.py .venv/bin/python -m pytest -q tests`. Disposable Postgres for SQL proofs: initdb under /var/tmp (postgres user cannot read /tmp/claude-*), port 55432, stop and delete afterward. No production changes, no provider calls.

- 2026-11-26 Claude: Reviewed repo from stale default branch; produced a roadmap later found stale (see section 3). Discovered 30+ newer remote branches, identified the two live development lines, confirmed production Vercel deploys are manual with unknown SHA. No production changes made. Wrote this handoff.
