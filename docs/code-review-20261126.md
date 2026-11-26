# Code review — November 26, 2026

Scope: the Facebook/leads line (this branch = `codex/facebook-attribution-resolution` + handoff docs). Method: tool-driven static review (ruff, vulture, radon, AST scans, targeted greps) plus the CI history. **Not** a line-by-line read of ~25k TS and ~22k Python lines; frontend `tsc`/ESLint could not run in the cloud sandbox (npm registry returned 403 for `@typescript-eslint/utils@8.57.1`), so frontend type/lint status relies on CI, which is green on commits 987–990.

Backend: 1187 tests pass (10 skipped). No code was changed by this review, deliberately, because other `codex/*` branches are mid-flight and broad edits would create merge conflicts. Apply fixes on the integrated trunk.

## 1. The CI failure in the screenshot

Run 986 (commit `76ac781`) failed the frontend job at `npm audit` (12 vulnerabilities: vite ≤6.4.3, zod <4.6.6, launch-editor chain). It ran on the **stale default-branch code**. After merging the real code (`b83e513`) runs 987–990 pass (`vite ^6.3.0`, `zod ^4.6.7`, lockfile already updated). Root cause: the old default branch is behind on dependency fixes, which is another reason to retire it (see handoff N2). Action: keep `npm audit` in CI (it caught a real issue); do not merge the stale default branch.

## 2. Findings (ranked)

### High
| # | Finding | Evidence | Fix |
|---|---|---|---|
| H1 | **Two divergent development lines** (acquisition `628fc02` vs Facebook/leads `e88a7c6`), ~30 `codex/*` branches, a stale default branch, manual Vercel deploys with no SHA. Highest operational risk: no single source of truth. | git branch comparison; Vercel deploy `source: cli`, `meta: {}` | Pick a trunk, merge lines, protect it, deploy from Git (or tag every manual deploy). Keep the `vercel.json` guard until then. |
| H2 | **Facebook attribution is empty in production**: `ad_campaigns` and `ad_creatives` have 0 rows, 0 of 9 Facebook leads attributed, so ad spend cannot be tied to leads. | Read-only production queries | Register mappings (needs Ads Manager IDs), apply reconcile migration, deploy wiring. |
| H3 | Five deployment targets are maintained (`Dockerfile`, `Procfile`, `fly.toml`, `railway.toml`, `render.yaml`, `nixpacks.toml`, `docker-compose.yml`, plus Vercel). Production uses Vercel (plus 3 Railway services that earlier notes say are not queue workers). Unused targets rot and confuse operators. | repo root | Declare Vercel the single target, delete or archive the rest after confirming Railway services are unused. |

### Medium
| # | Finding | Evidence | Fix |
|---|---|---|---|
| M1 | **Oversized, high-complexity modules.** `web/api/webhooks.py` 2,162 lines/56 functions; `web/api/__init__.py` 1,256; `lead_forms_api.py` 891; `Leads.tsx` 1,332; `Acquisitions.tsx` 1,087; `SetupWizard.tsx` 817. Radon grade F: `score_lead` (88), `record_chat_event` (57), `match_buyers_to_deal` (41); E: `enqueue` (36), `_readiness` (40). | radon cc | Split webhooks by provider (twilio/sendgrid/retell/facebook/vapi); extract scoring rules into table-driven rules with golden tests (golden tests already exist); decompose the three F functions first. |
| M2 | **Legacy stacks still wired**: VAPI (`tools/vapi_adapter.py` 594 lines, `config/vapi_prompt.py`, VAPI branches in `webhooks.py`) alongside Retell; Jinja pipeline UI (`web/templates/*`, `/v1/*`) alongside the React app. | grep | Confirm unused in production, then remove behind a deprecation commit. Saves ~1k+ lines and an attack surface. |
| M3 | **78 broad `except Exception` handlers** in backend. Several are intentional fail-closed paths, but swallowed errors hide root causes (the Oct 18 availability alert lost its real error for this reason). | grep | Log with context at minimum; narrow to specific exceptions on money/consent paths. |
| M4 | **57 `any` types** in the frontend and 149 baseline lint findings (the gate only blocks new ones). | grep, `lint-baseline.json` | Burn down per touched file; add the type-aware rule set as errors for new files. |
| M5 | Frontend queries Supabase directly from 16 components/pages plus 8 hooks (`supabase.from(`). Business rules (stage guards, QA exclusion) are enforced in SQL, which is good, but access patterns are scattered. | grep | Route through the existing hooks layer so components never call Supabase directly. |

### Low
| # | Finding | Fix |
|---|---|---|
| L1 | 87 unused imports (`F401`), 4 unused variables incl. `tools/batchdata_adapter.py:195` (`records` is computed from the response and never used — possibly a dropped phone-extraction feature, verify) and `tools/vapi_adapter.py:336` (`duration_ms`). | `ruff --fix` for F401; review the two variables by hand. |
| L2 | 57 `raise` inside `except` without `from` (B904), losing exception chains. | Add `from exc` / `from None`. |
| L3 | `web/api/lead_forms_api.py:777` re-imports `timedelta` (already imported line 31); 3 f-strings without placeholders (`main.py:149`, `tools/run_migrations.py:21`, `webhooks.py:1271`); `vapi_turns_to_text` imported but unused in `webhooks.py:51`. | Trivial cleanup. |
| L4 | `B008`: `File(...)` and request-model construction in argument defaults (`web/app.py:238,274`, `buyers_api.py:102`, `leads_api.py:34`, `web/api/__init__.py:717`). FastAPI tolerates `File()`; request-model defaults are shared mutable state. | Use `Annotated[..., File()]`; build models inside the handler. |
| L5 | The `F811` "redefinition" hits are pytest fixtures imported then used as arguments (false positives). Test files `test_schemas.py:72,75` use `pytest.raises(Exception)` (blind); `datetime.utcnow()` deprecation (367 warnings). | Tighten exception types; use `datetime.now(UTC)`. |
| L6 | Docs and evidence JSON on the Facebook branches add up (docs 1.5 MB here, much more on other branches). Hiring/recruiting runbooks live beside engineering docs. | Move recruiting docs to a separate folder; keep one `START-HERE` index. |

### Things that checked out (no action)
- No `eval`/`exec`/`pickle.loads`/`verify=False`/`shell=True` in backend code.
- No blocking `requests`/`time.sleep` inside `async def` handlers (AST scan found none).
- No duplicate route registrations.
- No browser-side Anthropic key or `dangerouslyAllowBrowser`; only the Supabase **anon** key is baked in (expected, RLS-protected).
- No `@ts-ignore`, no `console.log`, one `eslint-disable`.
- Migrations tested with rollback proofs; new reconcile function has a SQL proof.

## 3. Streamlining plan (highest leverage first)

1. **Unify trunk and deploy path** (H1, H3): one branch, Git-based deploys, one hosting target. Removes the most error-prone manual steps.
2. **Delete dead stacks** (M2, H3): VAPI, Jinja UI, unused host configs. Verify with production traffic/log queries before removal.
3. **Split `webhooks.py`** (M1): one module per provider with shared signature/idempotency helpers; target <500 lines each. Add contract tests per provider before splitting.
4. **Refactor the F-grade functions** with characterization tests (`score_lead`, `record_chat_event`, `match_buyers_to_deal`).
5. **Mechanical cleanup PR** (L1–L5): `ruff --fix` for F401, B904 chains, narrow blind `except`, trivial f-strings. Add `ruff` to CI with a baseline gate, the same pattern as `lint:check`.
6. **Frontend data layer** (M5) and `any` burn-down (M4), done opportunistically in files being edited.
7. **Dependency hygiene**: keep `npm audit` in CI; schedule monthly lockfile refreshes; pin the SheetJS tarball by hash.

## 4. Suggested CI additions
- `ruff check --select F,B904` with a baseline.
- `npm audit --audit-level=high` stays blocking; surface the vulnerable package in the job summary.
- Tag every manual Vercel deploy with the commit (`vercel deploy --meta githubCommitSha=$(git rev-parse HEAD)`).

## 5. Not covered
Line-by-line logic review of scoring rules, consent/suppression paths and RLS policies (these have extensive tests and prior acceptance evidence); the acquisition line (`628fc02`, 435 commits ahead); runtime/performance profiling; visual QA of the UI.
