# WholesaleOS — Step-by-Step User Guide

Each step below tells you exactly what to do, what the system does for you, and where to go next. Complete every step in order — the in-app guide on your Dashboard tracks your progress automatically.

---

## Step 1 of 11 — Complete Setup

**Where:** Setup Wizard (first login) · then Settings → API

### What you do
1. Register your account at `/register` — the first account is auto-promoted to admin
2. The Setup Wizard launches automatically on first login
3. Enter your API keys when prompted:
   - **Supabase URL + Anon Key** — from Supabase → Settings → API
   - **Anthropic API Key** — from console.anthropic.com
   - **Retell AI Agent ID + API Key** — from app.retellai.com → Agents
   - **Twilio Account SID + Auth Token + Phone Number** — from console.twilio.com
4. Click **Save Configuration**
5. Run all 7 database migrations in Supabase SQL Editor (001 through 007)

### What the system does
- Validates each API key on save
- Creates your user profile with admin role
- Initializes the database schema (leads, deals, buyers, calls, land leads)

### ✅ Step 1 complete when
Your Dashboard loads without errors and shows the Getting Started Guide.

---

## Step 2 of 11 — Choose Your Acquisition Strategy

**Where:** Dashboard → Strategy Comparison Panel

### What you do
1. Scroll to the **Strategy Comparison Panel** on your Dashboard
2. Read the three options side-by-side:
   - **Mass Outreach** — 30,000 leads, 2–4 contracts/month, high cost
   - **Precision Targeting** — 2,000 leads, 2–6 contracts/month, lowest cost *(recommended to start)*
   - **Stack-First Hybrid** — 5,000 leads, 4–8 contracts/month, best ROI at scale
3. Click **Select** on your chosen strategy

### What the system does
- Saves your selection (persists across sessions)
- Updates the Acquisition Funnel targets and conversion benchmarks
- Adjusts the lead import recommendations to match your strategy

### ✅ Step 2 complete when
You have selected a strategy and the Funnel Panel shows matching targets.

**→ Next: Import Your First Leads**

---

## Step 3 of 11 — Import Your First Leads

**Where:** Leads → Import CSV

### What you do
1. Get your lead list:
   - **Free (Phase 0):** Download your county's tax delinquent list (county assessor website, search "delinquent tax list")
   - **XLeads users:** Export your list as CSV from XLeads
   - **Vacant Land:** Use the **Vacant Land → Import XLeads** button on the `/land` page
2. Go to the **Leads** page → click **Import CSV**
3. Drag your CSV file into the upload area
4. Confirm the column mapping preview
5. Click **Import**

### Required CSV columns
| Column | Example |
|---|---|
| `owner_name` | John Smith |
| `property_address` | 123 Oak St |
| `city` | Dallas |
| `state` | TX |
| `owner_phone_1` | 2145550001 |

### What the system does
- Removes DNC/suppressed numbers automatically
- Calculates a **Distress Score** for every lead using signal stacking:
  - Vacant + Tax delinquent = +35 bonus
  - Probate + Vacant = +40 bonus
  - Code violation + Vacant = +40 bonus
- Assigns **Precision Tier** (1 = highest priority, score ≥ 80)
- Assigns a **Priority Rank** across all leads
- Fills the **Top 2,000 Priority List** with highest-ranked leads

### ✅ Step 3 complete when
You see leads in the Leads page with Tier and Score assigned.

**→ Next: Review Precision Targeting**

---

## Step 4 of 11 — Review Your Precision Targeting List

**Where:** Dashboard → Precision Targeting Panel

### What you do
1. Check the **Top 2,000 Priority List** progress bar
2. Confirm you have enough **Tier 1 leads** (score ≥ 80) — aim for 200+
3. Review the **Stack Analytics** table — which list types have the best conversion
4. Decision:
   - If Top 2,000 < 50% filled → import more leads before calling
   - If very few Tier 1 leads → source stacked lists (vacant + tax, vacant + probate)
   - If ready → proceed to launch

### What the system does
- Shows real-time tier breakdown and stack analytics
- Recalculates ranks as you import more leads

### ✅ Step 4 complete when
Your Top 2,000 list is populated and you can see Tier 1 leads ready to call.

**→ Next: Launch Your AI Calling Campaign**

---

## Step 5 of 11 — Launch Your AI Calling Campaign

**Where:** Leads → select leads → Launch Campaign

### What you do
1. Go to the **Leads** page
2. Filter by **Precision Tier: 1** to see your highest-priority leads
3. Click **Select All Filtered**
4. Click **Launch AI Dialing Campaign**
5. Confirm campaign settings:
   - Calling hours (default: 8 AM – 8 PM local time)
   - Max calls per hour
   - Retry attempts for no-answer
6. Click **Confirm & Launch**

### What the system does automatically for every call
- Dials the lead via Retell AI voice agent
- The AI agent introduces itself and asks qualifying questions:
  - Timeline to sell?
  - Property condition?
  - Is it occupied or vacant?
  - What price are you looking for?
- Records the full call and generates a transcript
- Extracts intent signals and calculates a **Qualification Score**
- Routes to HOT (≥80) / WARM (50–79) / COLD (<50)

### ✅ Step 5 complete when
You see calls appearing in the Acquisition Funnel on the Dashboard.

**→ Next: Monitor Call Activity**

---

## Step 6 of 11 — Monitor Call Activity

**Where:** Dashboard → Acquisition Funnel

### What you do
1. Check the Dashboard morning and evening while your campaign runs
2. Watch the funnel progress bars — healthy benchmarks for Precision strategy:
   - Contact rate (conversations ÷ calls): aim for **≥ 60%**
   - Interested rate: aim for **≥ 30%** of conversations
   - HOT lead rate: aim for **≥ 2%** of calls
3. If contact rate < 40%: check that phone numbers are formatted correctly in your CSV
4. If HOT rate is 0 after 200 calls: review a transcript in Acquisitions → WARM Leads to see what the AI is hearing

### What the system does
- Updates funnel metrics every 2 minutes
- Sends you a notification the moment a HOT lead is detected
- Pauses dialing on HOT leads automatically so you can follow up personally

### ✅ Step 6 complete when
You have 50+ calls completed and the funnel is updating.

**→ Next: Review Your HOT Leads**

---

## Step 7 of 11 — Review Your HOT Leads

**Where:** Acquisitions → HOT Leads tab

### What you do — within 1 hour of a HOT alert
1. Go to **Acquisitions → HOT Leads**
2. Open the lead card — review:
   - **Qualification score** (80–100+ = very motivated)
   - **Key signals** detected: timeline, condition, occupancy, price
   - **Key quotes** from the actual conversation
   - **Listen to recording** (link on the card)
3. Confirm these green flags before calling:
   - Seller mentioned a specific timeline ("need to sell in 2 weeks")
   - Property is vacant or has major repairs
   - Seller named a price or mentioned hardship
4. Call the seller personally — use the phone number on the card
5. Introduce yourself: *"Hi [name], I'm following up on a call you received earlier about your property at [address]…"*

### What the system already did before you called
- Paused all further AI calls to this lead
- Sent the seller an SMS follow-up
- Created a task with a 1-hour due time
- Saved the full transcript and extracted signals

### ✅ Step 7 complete when
You have spoken with at least one HOT lead and confirmed their motivation.

**→ Next: Run the AI Deal Analyzer**

---

## Step 8 of 11 — Run the AI Deal Analyzer

**Where:** Acquisitions → Deal Analysis tab

### What you do
1. Go to **Acquisitions → Deal Analysis**
2. Find the HOT lead and click **Run Deal Analysis**
3. Enter details you gathered from your call:
   - Confirmed square footage (if the seller knew)
   - Condition notes (what repairs did they describe?)
   - Seller's asking price
4. Click **Analyze**
5. Review the result:
   - Is **is_viable** = true?
   - Is the **projected assignment fee ≥ $10,000**?
   - Does the **exit strategy** match your buyer pool?
   - Are there any **weak deal reasons**?

### What the system does
- Estimates ARV using comparable sales data + Claude AI
- Assigns a **repair tier** based on condition signals:

| Tier | Cost/sqft | Condition |
|---|---|---|
| Light | $15–25 | Cosmetic — paint, carpet, fixtures |
| Moderate | $25–45 | Kitchen/bath, some systems |
| Heavy | $45–75 | Multiple systems, structural |
| Full Gut | $75+ | Mold, fire, severe damage |

- Calculates MAO: `(ARV × 70%) − Repair Cost − Holding Costs − Closing Costs − Assignment Fee`
- Generates offer range at 92–97% of MAO
- Recommends exit strategy (wholesale assignment, novation, wholetail, investor resale)

### ✅ Step 8 complete when
You have a viable deal analysis with an offer range you understand and believe.

**→ Next: Get Your Negotiation Brief**

---

## Step 9 of 11 — Use the Negotiation Intelligence Brief

**Where:** Acquisitions → Negotiation tab

### What you do
1. Go to **Acquisitions → Negotiation**
2. Find the lead and open the **Negotiation Brief**
3. Before calling, read:
   - **Opening Offer** (~85–88% of MAO) — start here
   - **Target Offer** (~92% of MAO) — where you aim to land
   - **Ceiling / MAO** — never exceed this
   - **Seller's pain points** — what they mentioned in the AI call
   - **Opening script** — use it word-for-word or adapt it
4. Call the seller and make your offer
5. Use the **Objection Handlers** when resistance comes:
   - "Your offer is too low" → the handler tells you exactly what to say
   - "I need to think about it" → same
5. Log the outcome — update the lead status after the call

### What the system generates for you
- Personalized opening script based on what the seller said in the AI call
- Opening/target/ceiling offer tied to your MAO calculation
- 5 pre-written objection handlers
- Motivation level rating (Low / Medium / High / Urgent)

### ✅ Step 9 complete when
Seller has verbally agreed to your offer range.

**→ Next: Schedule the Appointment**

---

## Step 10 of 11 — Set and Confirm the Appointment

**Where:** Acquisitions → Appointments tab

### What you do
1. While the seller is on the phone (or immediately after), go to **Acquisitions → Appointments**
2. Click **Schedule Appointment**
3. Enter:
   - Date and time
   - Type: Virtual walkthrough / In-person / Sign contract
4. Click **Confirm**
5. Before the appointment:
   - Re-read the Negotiation Brief
   - Have your purchase agreement template ready
   - Double-check the MAO hasn't changed

### What the system does
- Sends a confirmation SMS to the seller
- Sets a reminder SMS 24 hours before
- Adds the appointment to your Appointments tab with countdown

### ✅ Step 10 complete when
Appointment is scheduled and seller has confirmed attendance.

**→ Next: Close the Contract**

---

## Step 11 of 11 — Close the Contract

**Where:** Leads → deal record · then Pipeline

### What you do
1. Execute your **Purchase and Sale Agreement** (your attorney-prepared template)
2. Collect the earnest money deposit ($500–$2,000)
3. On the lead record, click **Attach Document** and upload the signed contract
4. Update lead status → **Under Contract**
5. Begin marketing the deal to your buyer list
6. When the deal closes (assignment or double close):
   - Update status → **Closed**
   - Enter the actual assignment fee received

### What the system does
- Creates a deal record linked to the lead
- Updates the Pipeline board (moves to Under Contract → Closed)
- Increments your "Closed This Month" KPI
- Records the assignment fee in stack analytics — this deal now improves the conversion rate for that lead source, making future targeting smarter

### ✅ Step 11 complete when
Deal status = Closed and assignment fee is logged.

---

## Congratulations — now repeat from Step 3

After your first contract, you have real data in the system. The Stack Analytics view now shows you which lead sources convert best. Use that data to:
- Source more leads from your highest-converting stacks
- Increase call volume (move to Hybrid or Scale strategy)
- Build your buyer list so you can move deals faster

The system gets smarter with every deal you close.

---

## Quick Reference

### Qualification Score Formula
| Signal | Points |
|---|---|
| Timeline ≤ 30 days | +30 |
| Timeline ≤ 60 days | +25 |
| Property vacant | +20 |
| Major repairs | +20 |
| Named a price | +15 |
| Not interested | −50 |
| Hung up | −20 |

**HOT** = score ≥ 80 · **WARM** = 50–79 · **COLD** = < 50

### Distress Stacking Bonuses
| Stack | Bonus |
|---|---|
| Utility shutoff + Vacant | +45 |
| Probate + Vacant | +40 |
| Code violation + Vacant | +40 |
| Vacant + Tax delinquent | +35 |
| Absentee + Vacant | +30 |
| 4+ signals ("Ultimate Distress") | +70 |

### HOT Lead Automation (fires automatically)
1. Dialing paused for this lead
2. SMS sent to seller within 60 seconds
3. Task created — due in 1 hour
4. Notification pushed to Dashboard

### MAO Formula
```
MAO = (ARV × 70%) − Repair Cost − Holding Costs − Closing Costs − Assignment Fee
Offer Range = 92–97% of MAO
```

### Monthly Cost by Phase
| Phase | Monthly Burn | Target Contracts | Target Revenue |
|---|---|---|---|
| 0 — Dry Run | $7–10 | 0 (test) | $0 |
| 1 — Proof of Concept | $160–200 | 1 | $10k |
| 2 — Validation | $400–600 | 2–4 | $20k–40k |
| 3 — Scale | $1,500–2,000 | 4–8 | $40k–80k |

---

## Module: FB Ads Command Center

**Where:** Sidebar → FB Ads · Route: `/fb-ads`

The FB Ads Command Center is a guided, battle-plan-enforced system for running Facebook Lead Ads targeting motivated home sellers in the DFW market. Every setting is locked to the approved strategy so you can't accidentally misconfigure a campaign.

---

### Sub-module 1 — Campaign Setup Wizard

**Where:** FB Ads → Campaigns → New Campaign

A 6-step wizard that walks you through building a compliant Facebook campaign. You cannot advance past any step until all required fields are complete.

#### Step 1 — Campaign Settings
- **Objective** and **Special Ad Category: Housing** are locked — required for legal compliance
- Set your daily budget ($20–$100 — the battle-plan approved range)
- Enable A/B testing (strongly recommended — allows the system to identify top creatives)
- Locked fields show a "Battle Plan Enforced" badge; you cannot change them

#### Step 2 — Audience Builder
Four panels:
1. **Custom Audiences** — upload CSV lists (pre-foreclosure, probate, tax delinquent, absentee). Auto-named `[Type]-[County]-[YYYY-MM-DD]`. Minimum 100 records required
2. **Targeting Signals** — 3-tier interest targeting matrix:
   - **Tier 1 (Distress Signals):** Pre-checked — foreclosure, bankruptcy, divorce, etc. Must have at least one or a custom audience to advance
   - **Tier 2 (Transition Signals):** Optional — relocation, senior living, etc.
   - **Tier 3 (Landlord Burnout):** Optional — property management, rental fatigue, etc.
3. **Demographics** — Homeowners filter locked ON; income range editable; county multi-select for DFW coverage
4. **Lookalike Readiness** — shows progress toward the 50-lead threshold needed to create a Lookalike Audience

#### Step 3 — Ad Set Configurator
- One ad set card auto-generated per detected segment (foreclosure, probate, divorce, etc.)
- Pre-populated with the approved segment headline — editable but validated by the battle plan
- Copy version switcher (A / B / C) with battle-plan approved copy per segment
- Audience Network placement locked OFF (excluded from battle plan)
- Budget allocation per ad set

#### Step 4 — Creative Studio
Three tabs:
- **Images** — upload creative with brand palette checklist (Navy #0A1628, Gold #F5A623, White). Checklist enforces: no smiling agents, no luxury homes, real DFW neighborhoods
- **Copy** — edit the three copy versions (A/B/C) per ad set. Click **Review with Claude** to get a compliance score, flag generic openers, and check for pain-point/local signal/CTA
- **Video** — specs checklist: 9:16 or 1:1, 15–30 sec, open captions, CTA in final 5 sec

#### Step 5 — Lead Form Builder
- 5 required fields are locked in: Property Address, Condition, Situation (multi-select), Timeline, Contact Preference
- Optional fields: email, asking price, occupancy status
- Full routing map shows how each Situation answer routes to a pipeline segment and Twilio SMS sequence

#### Step 6 — Pre-Flight Checklist
- Auto-validates every setting across all 5 prior steps
- Red "NOT READY" banner if any required item fails; green "READY TO LAUNCH" when all pass
- **Claude Campaign Intelligence** card: click to get AI-estimated CPL range (cold + retargeting) and one specific recommendation before you launch
- Click **Save Draft** at any step to preserve progress; **Launch** is available only when all checks pass

---

### Sub-module 2 — Active Campaigns Dashboard

**Where:** FB Ads → Campaigns tab

Shows all campaigns with live KPIs pulled from `fb_campaign_performance`:
- **Status badge**: Active / Draft / Paused
- **Daily budget**, total **Spend**, **Leads** count
- **CPL** color-coded: green (≤$35), yellow ($35–$40), red (>$40 = above battle plan threshold)
- **Contact %** and **Appt %**
- **Battle Plan Score** (0–100) computed by Claude against all compliance requirements

Actions:
- **Pause / Activate** toggle
- **Edit** — reopens the Campaign Wizard in edit mode

---

### Sub-module 3 — Lead Intake Router

**Where:** FB Ads → Lead Router tab

Real-time view of all inbound leads from Facebook Lead Ads (received via the `fb-lead-intake` Edge Function). Refreshes every 30 seconds.

**Summary strip:**
- HOT count (foreclosure, probate, divorce, taxes)
- WARM count (tired landlord, relocating)
- COLD count (just exploring)

**Lead feed** shows each lead with:
- Segment badge (HOT-URGENT, HOT-ESTATE, WARM-LANDLORD, etc.)
- SMS sent status (green check = Twilio fired within 60 sec)
- Contact dot (green = contacted, grey = pending)
- Appointment dot (green = set, grey = not yet)

**Routing logic** (automatic — no action required):
| Situation | Segment Tag | Priority |
|---|---|---|
| Foreclosure | HOT-URGENT | A |
| Behind on Taxes | HOT-TAX | A |
| Probate / Inherited | HOT-ESTATE | A |
| Divorce | HOT-LEGAL | A |
| Tired Landlord | WARM-LANDLORD | B |
| Relocating | WARM-RELOCATION | B |
| Just Exploring / Other | COLD-NURTURE | C |

---

### Sub-module 4 — Performance Tracker

**Where:** FB Ads → Performance tab

**KPI Strip** (top of page):
- Total Spend
- Total Leads
- Blended CPL (red if > $40 battle plan threshold)
- Contact Rate (red if < 40%)
- Appt Rate

**Charts:**
- CPL by Segment (bar chart) — see which audience segments are most efficient
- Lead Volume by Day (line chart, last 30 days)
- Situation Tag Distribution (pie chart) — see what's actually motivating your leads
- Budget vs Lead Volume (dual-axis) — track spend efficiency over time

**Claude Optimization Alerts:**
Click **Analyze Now** to send all performance data to Claude. Returns up to 5 alerts:
- **Urgent** (red): CPL > $40 for 5+ days, requires immediate creative rotation
- **Warning** (amber): Frequency > 3.0 (audience fatigue), contact rate < 40%
- **Info** (blue): 50 leads reached (Lookalike audience ready to build), positive trends

---

### Sub-module 5 — Battle Plan Reference Library

**Where:** FB Ads → Battle Plan tab

10 collapsible reference sections covering the complete approved Facebook Ads strategy. Each section has a **"Claude, explain this"** button — click it to get a plain-language explanation of *why* that rule exists and what happens if it's ignored.

Sections:
1. **Campaign Settings Reference** — locked settings and their legal/strategic rationale
2. **Targeting Signal Matrix** — all 23 interest signals across 3 tiers
3. **Segment Headline Library** — all 8 segments with A/B/C copy variants
4. **Visual Creative Specs** — image/video requirements
5. **Lead Form Structure** — required fields and answer options
6. **Routing Map** — situation → segment → Twilio sequence table
7. **Retargeting Cadence** — Day 1/3/7/14/30 re-engagement sequence
8. **KPI Targets & Optimization Rules** — thresholds that trigger automated alerts
9. **Lookalike Build Sequence** — how to scale from 50→200→closed deal audiences
10. **CAPI Setup Checklist** — Meta Conversions API for privacy-compliant tracking

---

### FB Ads Setup Checklist (First Time)

Complete these before your first campaign:

1. **Run migration 010** in Supabase SQL Editor (`010_fb_ads_command_center.sql`)
2. **Deploy the Edge Function**: `supabase functions deploy fb-lead-intake`
3. **Set Edge Function secrets** in Supabase Dashboard → Functions → Secrets:
   - `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY`
   - `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`
4. **Create a Facebook App** at developers.facebook.com → get App ID + Secret
5. **Subscribe your app** to your Facebook Page's `leadgen` events
6. **Set webhook URL** in Facebook App settings: `https://[your-domain]/webhooks/facebook/lead`
   - Set Verify Token to match `FACEBOOK_WEBHOOK_VERIFY_TOKEN` in your `.env`
7. **Run the Campaign Setup Wizard** at `/fb-ads` → New Campaign
8. **Use Facebook's Test Lead tool** (Ads Manager → Testing) to fire a test webhook and confirm a lead appears in the Lead Router tab

### Battle Plan CPL Targets

| Audience Type | Target CPL | Warning Threshold |
|---|---|---|
| Cold (custom + interest) | $18–$35 | > $40 |
| Retargeting | $8–$14 | > $20 |
| Lookalike 1% | $20–$30 | > $40 |

### Lookalike Trigger Points

| Milestone | Action |
|---|---|
| 50 form completions | Enable Lookalike 1% DFW from lead audience |
| Lookalike enabled | Shift 60% budget to Lookalike, 40% to proven cold creatives |
| 200 completions | Test Lookalike 2% and 3% tiers |
| Closed deal contacts | Upload quarterly for "best buyer" lookalikes |
