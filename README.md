# WholesaleOS — AI-Powered Real Estate Wholesale Automation

An end-to-end wholesale acquisition platform that automates lead scoring, AI voice dialing, seller qualification, deal analysis, and negotiation intelligence — driving 2–8 contracts/month from a precision-targeted list.

---

## Table of Contents

- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Quick Start](#quick-start)
- [Environment Variables](#environment-variables)
- [GitHub PAT Auth (Agent Push)](#github-pat-auth-agent-push)
- [Database Migrations](#database-migrations)
- [Deployment](#deployment)
- [Acquisition Strategies](#acquisition-strategies)
- [Known Issues](#known-issues)
- [Polish / Roadmap Items](#polish--roadmap-items)

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        React Frontend                         │
│  Dashboard · Leads · Acquisitions · Pipeline · Deal Analyzer  │
│  Precision Targeting · Strategy Comparison · Buyers · Reports │
└─────────────────────────┬────────────────────────────────────┘
                          │ Supabase JS client (RLS)
┌─────────────────────────▼────────────────────────────────────┐
│                     Supabase (Postgres)                        │
│  Tables: leads, ai_call_records, call_transcripts,            │
│          qualification_results, deal_analyses,                 │
│          offer_recommendations, priority_scores               │
│  Views: funnel_metrics, stack_analytics,                      │
│         precision_targeting_summary                           │
│  Triggers: notify_hot_lead, sync_deal_to_lead                 │
└──────────┬───────────────────────────────────────────────────┘
           │ REST
┌──────────▼───────────────────────────────────────────────────┐
│               FastAPI Backend (web/)                          │
│  POST /webhooks/retell   — 4 Retell AI event types           │
│  GET/POST /api/*         — CRUD + AI agent orchestration     │
└──────────┬────────────────────────────────────────────────────┘
           │
 ┌─────────┴──────────────────────────────┐
 │              AI Agents (agents/)        │
 │  qualification_agent.py   — HOT/WARM/COLD scoring          │
 │  deal_analyzer_agent.py   — ARV + MAO + repair tiers       │
 │  negotiation_intelligence_agent.py — briefs + scripts      │
 │  distress_scoring_agent.py — stacking bonuses              │
 │  seller_outreach_agent.py  — Retell AI call creation       │
 └──────────┬─────────────────────────────┘
            │ API calls
 ┌──────────▼───────────┐   ┌──────────────────────┐
 │    Retell AI          │   │  Launch Control SMS  │
 │  (voice dialer)       │   │  (HOT lead follow-up)│
 └───────────────────────┘   └──────────────────────┘
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui |
| State / Data | TanStack Query v5, Zustand, Supabase JS |
| Charts | Recharts |
| Backend | FastAPI, Python 3.11, Uvicorn/Gunicorn |
| Database | Supabase (Postgres 15), Row Level Security |
| AI | Anthropic Claude claude-sonnet-4-6 (qualification + deal analysis + negotiation) |
| Voice Dialer | Retell AI (all 4 webhook event types) |
| SMS | Launch Control |
| Deployment | Railway · Render · Fly.io · Docker |

---

## Quick Start

### Prerequisites

- Node.js 20+
- Python 3.11+
- A Supabase project
- A Retell AI account with an agent configured
- An Anthropic API key

### 1. Clone and install

```bash
git clone <repo>
cd Wholesale-automation

# Backend
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Frontend
cd frontend && npm install
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — see Environment Variables section below
```

### 3. Run database migrations

In your Supabase SQL Editor, run migrations in order:

```
frontend/supabase/migrations/001_initial_schema.sql
frontend/supabase/migrations/002_workflow_enhancements.sql
frontend/supabase/migrations/003_user_management.sql
frontend/supabase/migrations/004_distress_stacking.sql
frontend/supabase/migrations/005_call_transcripts.sql
frontend/supabase/migrations/006_deal_analyzer.sql
```

### 4. Start services

```bash
# Backend
python main.py
# or: docker-compose up

# Frontend (separate terminal)
cd frontend
npm run dev
```

Open `http://localhost:5173` — register the first user (auto-promoted to admin).

### 5. Run backend tests

```bash
source .venv/bin/activate
python -m pytest -q
```

---

## Environment Variables

### Backend (`.env` in project root)

| Variable | Description |
|---|---|
| `SUPABASE_URL` | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (bypasses RLS for webhooks) |
| `RETELL_API_KEY` | Retell AI API key |
| `RETELL_AGENT_ID` | Retell agent ID to use for outbound calls |
| `RETELL_FROM_NUMBER` | E.164 phone number registered in Retell |
| `RETELL_WEBHOOK_SECRET` | Secret for verifying Retell webhook signatures |
| `ANTHROPIC_API_KEY` | Claude API key for qualification + deal analysis |
| `LAUNCH_CONTROL_API_KEY` | Launch Control SMS key |
| `LAUNCH_CONTROL_FROM_NUMBER` | SMS sender number |

### Frontend (`frontend/.env`)

| Variable | Description |
|---|---|
| `VITE_SUPABASE_URL` | Same Supabase URL |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon key (public) |

---

## GitHub PAT Auth (Agent Push)

Use PAT-based HTTPS auth for non-interactive `git push` from agent runtime.

1. Inject secrets into runtime environment (not in committed files):
   - `GITHUB_PAT` (preferred) or `GH_PAT`
   - Optional `GITHUB_USERNAME` (default is `x-access-token`)
2. Configure repo-local credential flow and immediately run a safe dry-run push verification:

```bash
GITHUB_PAT=*** tools/configure_git_pat_credentials.sh
```

3. Optional: run verification again manually:

```bash
GITHUB_PAT=*** tools/verify_git_push_dry_run.sh
```

For rotation/revocation procedure, see `docs/github-pat-auth.md`.

---

## Database Migrations

| File | Contents |
|---|---|
| `001_initial_schema.sql` | Core tables: leads, campaigns, call records |
| `002_workflow_enhancements.sql` | Workflow states, task queue, notifications |
| `003_user_management.sql` | Profiles, roles, `is_approved()` RLS helper |
| `004_distress_stacking.sql` | Stack scoring, signal weights, bonus rules |
| `005_call_transcripts.sql` | Transcripts, qualification results, audit logs |
| `006_deal_analyzer.sql` | Deal analyses, repair estimates, offer recs, precision tiers |

---

## Deployment

### Docker (recommended for production)

```bash
docker-compose up --build
```

### Railway

```bash
railway up
# uses railway.toml — set env vars in Railway dashboard
```

### Render

Uses `render.yaml`. Set all env vars in Render service settings.

### Fly.io

```bash
fly deploy
# uses fly.toml
```

---

## Acquisition Strategies

Three strategies are available on the Dashboard → Strategy Comparison Panel:

| Strategy | Leads | Contracts/Mo | Cost/Contract | Best For |
|---|---|---|---|---|
| Mass Outreach | 30,000 | 2–4 | $3,000–$6,000 | Maximum coverage |
| Precision Targeting | 2,000 | 2–6 | $800–$2,000 | Lean ROI |
| Stack-First Hybrid (AI Rec) | 5,000 | 4–8 | $1,500–$3,500 | Best deal flow |

See [USER_MANUAL.md](USER_MANUAL.md) for the full step-by-step workflow.

---

## Known Issues

### Backend

1. **`_trigger_hot_lead_automation` is synchronous inside an async handler.**
   The function is called with a bare function call (not `await`), but internally makes Supabase REST calls via `httpx`. If the Supabase call is slow, the webhook response may time out (Retell expects a response within 3 seconds).
   _Fix:_ Refactor to `async def` and `await` it, or dispatch to a background task queue.

2. **ARV estimation falls back to a fixed heuristic when Claude is unavailable.**
   `deal_analyzer_agent.py._heuristic_arv()` returns `sqft * 85` as a market-agnostic placeholder. In high-value or rural markets this can be off by 50%+.
   _Fix:_ Integrate a real comp data source (Zillow API, BatchData, or PropStream) as the primary ARV source and use Claude only for interpretation.

3. **No retry logic on Launch Control SMS failures.**
   If the SMS API call fails for a HOT lead, the failure is logged but no retry is attempted. The notification task is still created, but the seller never gets the text.
   _Fix:_ Add `tenacity` retry decorator to the SMS call, or persist failed SMS jobs to a retry queue in Supabase.

4. **`precision_tier` and `priority_rank` are only set at import time.**
   If additional leads are imported later, existing leads are not re-ranked. A lead that was Tier 2 before a batch of Tier 1 leads is added will stay ranked as Tier 2.
   _Fix:_ Add a re-scoring endpoint (or scheduled job) that recomputes `priority_rank` across all leads in a targeting batch.

5. **Retell `call_transcript` events may arrive out of order.**
   The webhook handler upserts transcript chunks by `call_id`, but does not sort or merge chunks. If Retell delivers chunks out of order (common on slow networks), the stored transcript may be fragmented.
   _Fix:_ Store chunks with a `sequence_num` and assemble the full transcript only on `call_completed`.

### Frontend

7. **`StrategyComparisonPanel` and `FunnelPanel` sync via `localStorage` + `CustomEvent`.**
   This works within a single browser tab but does not sync across multiple open tabs or devices. If a user has the dashboard open on two screens and selects a different strategy on each, they show different data.
   _Fix:_ Persist the selected strategy in the `profiles` table and read it via Supabase on mount.

8. **`DealAnalyzer` page (`/analyzer`) and the Deal Analysis tab in `Acquisitions` are separate UI surfaces with no data link.**
   Running an analysis in `/analyzer` does not appear in `/acquisitions` and vice versa. This can confuse users who expect one unified deal analysis workflow.
   _Fix:_ Both surfaces should query the same `deal_analyses` table; the standalone `/analyzer` page should accept a `leadId` query param to pre-populate from a lead record.

9. **Supabase realtime subscriptions are not used — all panels poll on a fixed interval.**
   `FunnelPanel` and `PrecisionTargetingPanel` refetch every 60–120 seconds. HOT lead counts and funnel stages can be stale by up to 2 minutes.
   _Fix:_ Add a `supabase.channel()` subscription on `ai_call_records` INSERT to trigger an immediate query invalidation.

10. **No loading skeleton for `StrategyComparisonPanel` on slow connections.**
    The panel renders nothing until its static data initializes. While the data is hardcoded (not fetched), a flash of empty content is visible on low-end devices.
    _Fix:_ Add a minimum-height placeholder or skeleton to prevent layout shift.

### Infrastructure

11. **Migrations must be run manually in Supabase SQL Editor.**
    There is no automated migration runner. If migrations are run out of order (e.g., `006` before `005`), foreign key constraints and view dependencies will fail silently.
    _Fix:_ Add a `supabase db push` command to the build script, or implement a `--migrate` flag in `main.py` startup.

12. **`frontend/node_modules` is excluded from git (correct) but `package-lock.json` must be committed.**
    Running `npm install` without an existing `package-lock.json` can resolve to different dependency versions across environments.
    _Status:_ `package-lock.json` is committed as of the last release.

---

## Polish / Roadmap Items

### High priority

- [ ] **Supabase realtime for HOT lead alerts** — replace polling with a live channel subscription so HOT lead notifications appear instantly in the dashboard
- [ ] **Re-score endpoint** — `POST /api/leads/rescore` recalculates `priority_rank` and `precision_tier` for all leads in a batch after new imports
- [ ] **ARV comp integration** — replace heuristic ARV with a real data source (BatchData, PropStream, or Zillow)

### Medium priority

- [ ] **Mobile-responsive Acquisitions tabs** — the 5-tab layout collapses poorly on screens < 768px; needs a scrollable tab bar and stacked cards
- [ ] **Bulk SMS to WARM leads** — add a "Send follow-up SMS to all WARM" button on the WARM Leads tab
- [ ] **Export to CSV** — add download buttons to Leads, Acquisitions, and Stack Analytics views
- [ ] **Email notifications for HOT leads** — supplement in-app notification + SMS with an email alert for operators who are not watching the dashboard
- [ ] **Appointment calendar integration** — sync confirmed appointments to Google Calendar or Calendly via webhook
- [ ] **Strategy selection persisted to user profile** — move from `localStorage` to `profiles.strategy_preference` column (see Known Issue #7)

### Lower priority

- [ ] **Dark mode** — Tailwind `dark:` class variants are partially implemented but not togglable via the UI
- [ ] **Deal comparison view** — side-by-side comparison of up to 3 deals with ARV/MAO/fee diff
- [ ] **Lead deduplication on import** — detect and merge leads with matching phone numbers or addresses across different batch imports
- [ ] **Investor buyer matching** — auto-suggest buyers from the Buyers table whose buy-box matches a newly analyzed deal's ARV/price range and exit strategy
- [ ] **Retell agent script versioning** — store the qualifying script version used for each call so A/B testing of agent scripts is possible
- [ ] **Integration tests for webhook pipeline** — end-to-end test: mock Retell event → qualification → HOT automation → Supabase assertions
- [ ] **Audit log UI** — expose the `audit_logs` table (created in migration 005) in the Admin panel so admins can review system actions
- [ ] **Batch calling schedule UI** — let users set per-state calling hours in the dashboard instead of only in `.env`
- [ ] **Voicemail drop** — detect voicemail answering machine and play a pre-recorded message instead of hanging up (Retell supports this natively)

---

## User Manual

For a full step-by-step workflow guide, see [USER_MANUAL.md](USER_MANUAL.md) or open **Help → User Manual** in the app sidebar.
