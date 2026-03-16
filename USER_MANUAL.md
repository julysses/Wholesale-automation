# AI Wholesale Automation Platform — User Manual

**Version:** 2.0 (Precision Targeting + AI Deal Analyzer)
**Last Updated:** March 2026

---

## Table of Contents

1. [Overview](#1-overview)
2. [Quick-Start Checklist](#2-quick-start-checklist)
3. [Step 1 — Initial Setup & Configuration](#3-step-1--initial-setup--configuration)
4. [Step 2 — Choose Your Acquisition Strategy](#4-step-2--choose-your-acquisition-strategy)
5. [Step 3 — Import & Score Your Leads](#5-step-3--import--score-your-leads)
6. [Step 4 — Review the Precision Targeting Dashboard](#6-step-4--review-the-precision-targeting-dashboard)
7. [Step 5 — Launch AI Dialing Campaign](#7-step-5--launch-ai-dialing-campaign)
8. [Step 6 — Monitor Live Call Activity](#8-step-6--monitor-live-call-activity)
9. [Step 7 — Review HOT Leads (Immediate Action Required)](#9-step-7--review-hot-leads-immediate-action-required)
10. [Step 8 — Run the AI Deal Analyzer](#10-step-8--run-the-ai-deal-analyzer)
11. [Step 9 — Use Negotiation Intelligence](#11-step-9--use-negotiation-intelligence)
12. [Step 10 — Set & Confirm Appointments](#12-step-10--set--confirm-appointments)
13. [Step 11 — Close the Contract](#13-step-11--close-the-contract)
14. [Dashboard Reference](#14-dashboard-reference)
15. [Automation Rules Quick Reference](#15-automation-rules-quick-reference)
16. [Troubleshooting](#16-troubleshooting)

---

## 1. Overview

This platform automates the most time-consuming parts of real estate wholesaling:

| What the System Does Automatically | What You Do |
|------------------------------------|-------------|
| Scores and ranks every imported lead | Choose strategy + approve lead batch |
| Dials leads via AI voice agent (Retell AI) | Review HOT lead alerts and respond |
| Transcribes every call and extracts intent signals | Validate deal analysis numbers |
| Qualifies HOT/WARM/COLD automatically | Negotiate using the AI-generated brief |
| Calculates ARV, MAO, and offer range | Sign the purchase agreement |
| Sends SMS follow-up on HOT leads | Build investor buyer relationships |
| Pauses dialing when a HOT lead is found | Track closings in the system |
| Books appointments and sends reminders | Show up to the appointment |

**Expected outcome (Precision strategy):** 2 – 6 contracts/month from 2,000 targeted leads, averaging $10,000+ per contract.

---

## 2. Quick-Start Checklist

Complete these one-time setup items before running your first campaign:

- [ ] Supabase project created and migrations 001–006 run
- [ ] Retell AI account created — Agent ID and API key saved
- [ ] Launch Control SMS account configured (for HOT lead follow-up)
- [ ] `.env` file populated (see Step 1)
- [ ] Frontend deployed and accessible in browser
- [ ] At least one lead list imported (CSV with required columns)

---

## 3. Step 1 — Initial Setup & Configuration

### What YOU need to do:

#### 1a. Run the database migrations

Open your Supabase project → SQL Editor → run each migration in order:

```
supabase/migrations/001_initial_schema.sql
supabase/migrations/002_rls_policies.sql
supabase/migrations/003_leads_scoring.sql
supabase/migrations/004_call_records.sql
supabase/migrations/005_call_transcripts.sql
supabase/migrations/006_deal_analyzer.sql
```

**How to verify:** Go to Table Editor — you should see tables including `leads`, `ai_call_records`, `call_transcripts`, `qualification_results`, `deal_analyses`, `offer_recommendations`.

#### 1b. Configure environment variables

Edit `.env` (copy from `.env.example`):

```env
# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Retell AI
RETELL_API_KEY=your-retell-api-key
RETELL_AGENT_ID=your-agent-id
RETELL_FROM_NUMBER=+1XXXXXXXXXX
RETELL_WEBHOOK_SECRET=your-webhook-secret

# SMS (Launch Control)
LAUNCH_CONTROL_API_KEY=your-lc-key
LAUNCH_CONTROL_FROM_NUMBER=+1XXXXXXXXXX

# AI (Claude)
ANTHROPIC_API_KEY=your-anthropic-key
```

#### 1c. Start the backend

```bash
docker-compose up -d
# or for local dev:
python main.py
```

#### 1d. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

**Proceed to Step 2 when:** The dashboard loads without errors and you can see the Acquisition Funnel on the main Dashboard page.

---

## 4. Step 2 — Choose Your Acquisition Strategy

### Navigate to: Dashboard → Strategy Comparison Panel

Three strategies are available. The system shows you side-by-side metrics to help you decide:

| Strategy | Lead Volume | Cost Index | Contracts/Mo | Best For |
|---|---|---|---|---|
| **Mass Outreach** (Old Blueprint) | 30,000 | $$$$ | 2–4 | Maximum market coverage |
| **Precision Targeting** (PRD v2) | 2,000 | $ | 2–6 | Lean teams, max ROI |
| **Stack-First Hybrid** (AI Recommended) | 5,000 | $$ | 4–8 | Growing teams, best deal flow |

**AI Recommendation:** Stack-First Hybrid delivers 4× better conversion than Mass Outreach and 2× more contracts than Precision alone, at roughly $500–$800 per contract.

### What YOU need to do:

1. Read the three strategy cards on the Dashboard
2. Click **Select** on your preferred strategy
3. Your selection is saved automatically — both the Funnel Panel and Comparison Panel stay in sync

**The system does:** Locks in the funnel targets and conversion benchmarks for your selected strategy. All progress bars and projected revenue will now reflect those targets.

**Proceed to Step 3 when:** You have selected a strategy and can see the matching targets in the Acquisition Funnel.

---

## 5. Step 3 — Import & Score Your Leads

### Navigate to: Leads page → Import

### What YOU need to do:

#### 3a. Prepare your lead list (CSV)

Required columns:

| Column | Description | Example |
|---|---|---|
| `owner_name` | Property owner full name | John Smith |
| `property_address` | Full street address | 123 Oak St |
| `city` | City | Dallas |
| `state` | 2-letter state | TX |
| `zip` | ZIP code | 75201 |
| `phone` | Primary phone | 2145550001 |
| `stack_name` | Which list this lead came from | Vacant+Tax |

**Optional but strongly recommended** (increases precision tier accuracy):

| Column | Description |
|---|---|
| `vacant` | true/false — is the property vacant? |
| `tax_delinquent` | true/false |
| `utility_shutoff` | true/false |
| `code_violation` | true/false |
| `probate` | true/false |
| `pre_foreclosure` | true/false |
| `absentee_owner` | true/false |
| `high_equity` | true/false |

#### 3b. Upload the CSV

Go to the Leads page → click **Import CSV** → drag your file → click **Import**.

**The system does automatically after import:**

- Removes DNC/suppressed numbers
- Calculates a **Distress Score** for every lead using stacking bonuses:
  - Utility shutoff + Vacant = +45 bonus
  - Probate + Vacant = +40 bonus
  - Code violation + Vacant = +40 bonus
  - Vacant + Tax delinquent = +35 bonus
  - Absentee + Vacant = +30 bonus
- Assigns a **Precision Tier**:
  - **Tier 1** (score ≥ 80): 1 deal per 200–700 records — your top priority
  - **Tier 2** (score 50–79): 1 deal per 500–1,200 records
  - **Tier 3** (score < 50): 1 deal per 2,000–4,000 records
- Assigns a **Priority Rank** (1 = highest) across all imported leads
- Fills the **Top 2,000 Priority List** with the highest-ranked leads

**Proceed to Step 4 when:** Import completes and you can see lead counts in the Precision Targeting Panel.

---

## 6. Step 4 — Review the Precision Targeting Dashboard

### Navigate to: Dashboard → Precision Targeting Panel

Before launching any calls, confirm your lead quality.

### What YOU need to do:

Review these key numbers:

| Metric | What to look for |
|---|---|
| **Top 2,000 Priority List %** | Should be 100% before launching (all 2,000 slots filled) |
| **Tier 1 count** | More Tier 1 leads = better results. Aim for 200+ Tier 1 |
| **Suppressed / DNC** | High suppression is normal — those are scrubbed correctly |
| **Deals by List Stack** | After your first campaign, check which stacks convert best |

### Decision point:

- **Top 2,000 list < 50% filled** → Import more leads before calling
- **Very few Tier 1 leads** → Source better stacked lists (vacant + tax + code violations)
- **Ready (Top 2,000 = 100%)** → Proceed to Step 5

**The system does:** Continually recalculates tier assignments as you import more leads. The progress bar updates in real time.

---

## 7. Step 5 — Launch AI Dialing Campaign

### Navigate to: Leads page → select leads → Launch Campaign

### What YOU need to do:

1. Filter leads to **Top 2,000** (or your target batch)
2. Click **Select All Filtered**
3. Click **Launch AI Dialing Campaign**
4. Confirm the campaign settings:
   - Calling hours: 8 AM – 8 PM local time (set per state)
   - Max calls per hour
   - Retry attempts for no-answer
5. Click **Confirm & Launch**

**The system does automatically for every call:**

- Initiates the call via Retell AI voice agent
- The AI agent introduces itself, qualifies the seller with natural conversation
- Listens for these intent signals:
  - **Timeline to sell** (within 30 days = highest priority)
  - **Property condition** (major repairs needed = motivated seller)
  - **Occupancy status** (vacant = high distress)
  - **Price expectation** (named a price = ready to negotiate)
  - **Interest level** (any negative signal removes from active dialing)
- Full call recording + transcript saved automatically
- Disposition recorded: `hot`, `warm`, `cold`, `no_answer`, `voicemail`, `not_interested`, `dnc`

**You do not need to monitor individual calls.** The funnel dashboard updates live.

**Proceed to Step 6 when:** The campaign is running and you see calls appearing in the Acquisition Funnel.

---

## 8. Step 6 — Monitor Live Call Activity

### Navigate to: Dashboard (main page)

The Acquisition Funnel updates every 2 minutes automatically.

### What to watch:

| Funnel Stage | Healthy Benchmark (Precision strategy) |
|---|---|
| AI Calls Made | Working toward 1,500 target |
| Conversations (contacted) | ~75% contact rate |
| Interested | ~30% of conversations |
| Warm / Hot Leads | ~27% of interested |
| Appointments Set | ~27% of warm/hot |
| Contracts Closed | ~42% of appointments |

**Progress bar colors:**
- Green (≥ 80% of target): on track
- Yellow (50–79%): needs attention
- Red (< 50%): behind — may need to add more leads or check dialer settings

### What YOU need to do during a campaign:

- Check the Dashboard morning and evening
- Watch for **HOT Lead alerts** (these require immediate action — see Step 7)
- If the contact rate is < 50%, verify your phone numbers are formatted correctly

**Proceed to Step 7 when:** You receive a HOT lead notification.

---

## 9. Step 7 — Review HOT Leads (Immediate Action Required)

### Navigate to: Acquisitions → HOT Leads tab

When the AI agent scores a seller as HOT (qualification score ≥ 80), the system:

1. **Immediately pauses dialing** for that lead (no more robocalls to this person)
2. **Sends an SMS** via Launch Control within 60 seconds
3. **Creates a follow-up task** assigned to you
4. **Posts a notification** in the dashboard
5. **Saves the full transcript** and extracted signals

### What YOU need to do — within 1 hour of HOT alert:

#### 7a. Read the qualification summary

On the HOT Leads tab, each lead card shows:

- **Qualification score** (80–100+ = extremely motivated)
- **Key signals detected:** timeline, condition, occupancy, price
- **Score breakdown:** which signals contributed how many points
- **Key quotes** from the actual conversation
- **Listen to recording** link

#### 7b. Confirm the lead quality

Look for these green flags:
- Mentioned a specific timeline ("I need to sell in 2 weeks")
- Property is vacant or has major repair issues
- Named a price (even if high — shows willingness to negotiate)
- Mentioned hardship (divorce, probate, financial stress)

#### 7c. Call the seller personally

Use the phone number on the lead card. Introduce yourself as a follow-up to the earlier call. The seller is warm — they already spoke with the AI agent.

**The system does:** Logs your manual call when you update the lead status after your conversation.

**Proceed to Step 8 when:** The seller is interested in an offer and you need to know what to offer.

---

## 10. Step 8 — Run the AI Deal Analyzer

### Navigate to: Acquisitions → Deal Analysis tab

### What YOU need to do:

#### 8a. Trigger analysis for a lead

On the HOT Lead card or the Deal Analysis tab:

1. Find the lead
2. Click **Run Deal Analysis**
3. Enter any additional property details you gathered from your call:
   - Confirmed square footage (if known)
   - Condition details (what repairs did the seller mention?)
   - Asking price (if seller named one)
4. Click **Analyze**

**The system does automatically:**

- Estimates ARV (After Repair Value) using comparable sales data
- Assigns a repair tier based on condition signals:

| Repair Tier | Cost/sqft | Condition |
|---|---|---|
| Light | $15–$25 | Cosmetic only — paint, carpet, fixtures |
| Moderate | $25–$45 | Kitchen/bath updates, some systems |
| Heavy | $45–$75 | Multiple systems, structural concerns |
| Full Gut | $75+ | Gut renovation, mold, fire, severe damage |

- Calculates MAO using the PRD formula:
  ```
  MAO = (ARV × 70%) − Repair Cost − Holding Costs − Closing Costs − Assignment Fee
  ```
- Generates offer range: 92%–97% of MAO (room to negotiate)
- Recommends exit strategy:
  - **Wholesale Assignment** — standard wholesale, assign contract to investor
  - **Novation Agreement** — seller stays on title, you market on MLS
  - **Wholetail** — light cosmetic flip before assigning
  - **Investor Resale** — deep value deal for buy-and-hold investor

#### 8b. Review the analysis

Check:
- Is the **ARV confidence** medium or high? (Low = need more comps)
- Is the deal **viable** (is_viable = true)?
- Is the **projected assignment fee** ≥ $10,000?
- Does the **exit strategy** match your buyer pool?

**If the deal looks weak:** The system shows `weak_deal_reasons`. Common reasons: ARV too uncertain, repair cost exceeds spread, seller price too high.

**Proceed to Step 9 when:** The deal is viable and you have your offer range.

---

## 11. Step 9 — Use Negotiation Intelligence

### Navigate to: Acquisitions → Negotiation tab

### What YOU need to do:

1. Find the lead on the Negotiation tab
2. Review the **Negotiation Brief** (generated from the call transcript + deal analysis):

#### The brief includes:

**Offer Structure:**
| Level | Amount | When to Use |
|---|---|---|
| Opening Offer | ~85–88% of MAO | Start here |
| Target Offer | ~92% of MAO | Where you aim to land |
| Ceiling Offer (MAO) | = MAO exactly | Never exceed this |

**Seller Intelligence:**
- **Motivation level:** Low / Medium / High / Urgent
- **Pain points:** What the seller mentioned (foreclosure deadline, job loss, estate, etc.)
- **Primary exit strategy recommendation**

**Opening Script:**
The system generates a personalized opening script based on what the seller said in the AI call. Use it word-for-word or adapt it.

**Objection Handlers:**
Pre-built responses to the most common seller objections:
- "Your offer is too low"
- "I need to think about it"
- "I already have an agent"
- "I owe more than that"
- "My neighbor got more"

#### What YOU do with this:

3. Read the opening script before calling
4. Have the offer range visible during negotiation
5. Start at the opening offer
6. Use the objection handlers when resistance comes up
7. Never go above the ceiling offer (MAO) — deals above MAO do not pencil

**The system does:** Updates the lead status when you log the negotiation outcome.

**Proceed to Step 10 when:** The seller verbally agrees to your offer range.

---

## 12. Step 10 — Set & Confirm Appointments

### Navigate to: Acquisitions → Appointments tab

### What YOU need to do:

#### 10a. Schedule the appointment

After verbal agreement:

1. On the lead card, click **Schedule Appointment**
2. Select date and time
3. Add appointment type: Virtual walkthrough / In-person / Sign contract
4. Click **Confirm**

**The system does:**
- Sends a confirmation SMS to the seller
- Adds the appointment to your Appointments tab
- Sends a reminder SMS 24 hours before

#### 10b. Prepare for the appointment

Before the appointment:
- Re-read the Negotiation Brief
- Have the purchase agreement template ready
- Review the deal analysis one more time — confirm MAO has not changed

#### 10c. Complete the appointment

After the appointment:
- Go to Appointments tab
- Mark the appointment as **Completed** or **No Show**
- If completed → update lead status to **Contract** (if signed) or **Back to Follow-up**

**The system does:** Updates all funnel metrics. A completed appointment counts as a conversion in the funnel.

---

## 13. Step 11 — Close the Contract

### Navigate to: Leads → the specific lead record

### What YOU need to do:

1. Execute the Purchase and Sale Agreement (your attorney-prepared template)
2. Collect the escrow deposit (typically $500–$2,000 earnest money)
3. Upload the signed contract to the lead record (click **Attach Document**)
4. Update lead status to **Contract**
5. Begin marketing to your buyer list

**The system does:**
- Records the contract in the database
- Updates the Funnel Panel's "Contracts Closed" counter
- Calculates and displays projected revenue based on contracts closed × $10,000 avg fee

### After assignment:

6. When the deal closes (double close or assignment), update status to **Closed**
7. Enter the actual assignment fee received
8. The system updates stack analytics — this deal now counts toward conversion rate for that lead source

**This data improves future campaigns:** The Stack Analytics view shows which list stacks are generating the most deals, so you know where to spend more on list acquisition.

---

## 14. Dashboard Reference

### Main Dashboard

| Panel | What it shows | Refresh rate |
|---|---|---|
| KPI Summary | Total calls, HOT leads, contracts, revenue | 2 min |
| Acquisition Funnel | Actual vs target for each funnel stage | 2 min |
| Strategy Comparison | Side-by-side conversion rates + ROI | Static |
| Precision Targeting | Top 2,000 list status + stack analytics | 1 min |

### Acquisitions Page (5 tabs)

| Tab | Shows | Action available |
|---|---|---|
| HOT Leads | Score ≥ 80, immediate action needed | Call, analyze, schedule |
| WARM Leads | Score 50–79, follow-up queue | Send SMS, schedule callback |
| Deal Analysis | ARV / repair / MAO cards | Run or re-run analysis |
| Negotiation | Offer briefs, scripts, objection handlers | Generate or view brief |
| Appointments | Upcoming + completed appointments | Mark complete, reschedule |

### Status definitions

| Lead Status | Meaning |
|---|---|
| `new` | Just imported, not yet called |
| `contacted` | AI agent reached the seller |
| `warm` | Showed interest, not yet HOT |
| `hot` | Qualification score ≥ 80, ready for offer |
| `appointment_set` | Meeting scheduled |
| `contract` | Purchase agreement signed |
| `closed` | Assignment fee collected |
| `not_interested` | Seller declined |
| `dnc` | Do Not Call — removed from all campaigns |
| `suppressed` | Manually removed from outreach |

---

## 15. Automation Rules Quick Reference

### HOT Lead Trigger (score ≥ 80)
Fires when qualification score crosses 80:
1. Dialing paused for this lead
2. SMS sent via Launch Control
3. Task created for you
4. Notification pushed to dashboard

### Qualification Scoring Formula

| Signal | Points |
|---|---|
| Timeline: within 30 days | +30 |
| Timeline: within 60 days | +25 |
| Timeline: within 90 days | +15 |
| Timeline: flexible | +10 |
| Property vacant | +20 |
| Major repairs needed | +20 |
| Some repairs needed | +15 |
| Named a price | +15 |
| Not interested | −50 |
| Hung up | −20 |

**HOT** = score ≥ 80 | **WARM** = 50–79 | **COLD** = < 50

### Distress Stacking Bonuses (lead scoring)

| Stack Combination | Bonus |
|---|---|
| Utility shutoff + Vacant | +45 |
| Probate + Vacant | +40 |
| Code violation + Vacant | +40 |
| Vacant + Tax delinquent | +35 |
| Absentee + Vacant | +30 |
| 4+ signals stacked ("Ultimate Distress") | +70 |

---

## 16. Troubleshooting

### "My leads aren't getting Tier 1 scores"

- Check that your CSV includes distress signal columns (`vacant`, `tax_delinquent`, etc.)
- Single-signal lists (absentee only, or tax only) will rarely hit Tier 1
- Source stacked lists — ask your data provider for Vacant + Tax, or Vacant + Pre-foreclosure

### "No HOT leads after 500 calls"

- Check call dispositions in Acquisitions → WARM Leads — are any scoring 60–79?
- Review a transcript to see if the AI agent is asking qualifying questions correctly
- Verify the Retell agent prompt includes the qualification framework
- Consider switching to Stack-First Hybrid strategy to increase call volume

### "Deal Analyzer shows 'Not Viable'"

The system shows `weak_deal_reasons`. Common fixes:
- **ARV too low / repairs too high** → verify square footage and condition with the seller
- **Seller's asking price above MAO** → use the negotiation script to educate the seller
- **Low ARV confidence** → the system needs more comps; manually check Zillow/MLS for the area

### "Webhook events not arriving from Retell"

1. Verify `RETELL_WEBHOOK_SECRET` in `.env` matches your Retell dashboard
2. Confirm your backend URL is publicly accessible (use ngrok for local dev)
3. In Retell dashboard, check the webhook delivery log for error responses
4. Check backend logs: `docker-compose logs web`

### "Frontend shows blank data / loading spinners"

1. Confirm `.env` in `frontend/` has the correct `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`
2. Verify migrations 001–006 ran without errors in Supabase SQL Editor
3. Check Supabase dashboard → Authentication → confirm your user is approved (RLS requires `is_approved()`)

### "Calls going out but not updating the funnel"

- Retell webhooks may not be reaching the backend
- Check: `POST /webhooks/retell` is accessible from the internet
- Verify Retell agent configuration points to your webhook URL
- Test with a manual webhook delivery in Retell dashboard

---

## Getting Help

For questions or issues:
- Check Supabase logs: Project → Logs → API
- Check backend logs: `docker-compose logs -f web`
- Check frontend console: Browser DevTools → Console tab
- Review the Retell AI documentation at [docs.retellai.com](https://docs.retellai.com)

---

*This manual covers platform version 2.0 with Precision Targeting and AI Deal Analyzer. For the legacy Mass Outreach workflow, select the "Mass Outreach" strategy on the Strategy Comparison Panel — all steps remain the same, only the lead volume and funnel targets change.*
