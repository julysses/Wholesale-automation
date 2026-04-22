# Week-2 Recruiting Run: AI Dialer Operations Specialist

Issue link: [THE-53](/THE/issues/THE-53)
Execution week: April 28 - May 4, 2026
Owner: Acquisition Manager

## 1) Role Brief (Published)

### Role mission
Ensure 100% reliability of AI-driven outbound calling campaigns, maintaining high connect rates and seamless lead routing from Retell AI/Vapi into the CRM.

### Scope
- Execute and monitor daily outbound campaigns across Retell AI and BatchDialer.
- Maintain data hygiene using BatchData to ensure high-quality lead lists.
- Monitor webhook health and call event completeness (Target: 98%+).
- Troubleshoot and resolve failed dialer jobs or API integrations (Target: <2% failure rate).
- Route HOT leads to Acquisitions Closers within 5 minutes of call completion.
- Optimize campaign performance (connect rates, sentiment analysis) through list tuning and timing adjustments.

### Success metrics (first 30 days)
- Campaign reliability: < 2% failed jobs.
- Webhook/Call event completeness: >= 98%.
- HOT lead routing latency: <= 5 minutes.
- Connect rate improvement: Weekly positive trend.
- System uptime: 99.9% for dialer operations.

### Required profile
- 2+ years experience in AI dialer operations (Retell AI, Vapi, or similar).
- Proficiency with BatchDialer and BatchData.
- Strong technical troubleshooting skills (webhooks, API logs, JSON).
- High-volume sales operations or real estate wholesaling background preferred.
- Analytical mindset with a focus on funnel optimization.

## 2) Funnel Design (Stages, Owners, SLA)

| Stage | Owner | SLA | Exit criteria |
|---|---|---|---|
| Sourced | Acquisition Manager | same day | Profile meets minimum dialer ops criteria |
| Recruiter Screen Scheduled | Acquisition Manager | <= 24h from shortlist | Candidate confirms screen slot |
| Recruiter Screen Completed | Acquisition Manager | <= 48h from scheduling | Candidate passes communication + technical aptitude bar |
| Practical Exercise Assigned | Acquisition Manager | <= 24h after pass | Candidate receives "Broken Campaign Diagnosis" exercise |
| Practical Exercise Reviewed | Acquisition Manager | <= 24h after submission | Accurately identifies root cause in logs and proposes fix |
| Final Interview | Acquisition Manager | <= 48h after exercise pass | Culture fit + Ownership/Escalation judgment confirmed |
| Offer Decision | Acquisition Manager + CEO | <= 24h post-final | Offer/no-offer decision recorded |

## 3) Practical Exercise: Diagnose a Broken Outbound Campaign

### Objective
Assess the candidate's ability to identify technical failures in a complex AI dialer stack using sample logs.

### Scenario
The candidate is provided with a snippet of logs from a failed morning campaign. The campaign shows "0 calls connected" despite 500 leads being queued.

### Sample Logs for Exercise
```json
[
  {"timestamp": "2026-04-28T08:00:01Z", "event": "campaign_started", "campaign_id": "outbound_dfw_001", "leads_queued": 500},
  {"timestamp": "2026-04-28T08:00:05Z", "event": "dialer_job_created", "job_id": "job_8821", "provider": "RetellAI"},
  {"timestamp": "2026-04-28T08:00:10Z", "event": "webhook_received", "type": "call.initiated", "call_id": "call_v1_992"},
  {"timestamp": "2026-04-28T08:00:11Z", "event": "webhook_error", "type": "call.initiated", "error": "401 Unauthorized", "target": "https://api.wholesaleos.com/webhooks/retell"},
  {"timestamp": "2026-04-28T08:00:15Z", "event": "dialer_job_failed", "job_id": "job_8821", "reason": "Consecutive webhook failures exceeded threshold (1)"},
  {"timestamp": "2026-04-28T08:05:00Z", "event": "monitoring_alert", "severity": "critical", "message": "Campaign outbound_dfw_001 stalled. No active calls."}
]
```

### Evaluation Criteria
- **Root Cause Identification**: Correctly identifies that the API Key/Token for the webhook endpoint has expired or is invalid (401 Unauthorized).
- **Impact Assessment**: Recognizes that the entire campaign is blocked and no leads are being contacted.
- **Resolution Plan**: Proposes checking the environment variables/secrets in the CRM/Middleware and verifying the Retell AI API key.
- **Speed to Action**: Explains how they would have detected this in real-time (monitoring alerts) rather than waiting for 5 minutes.

## 4) Final Interview Questions (Acquisition Manager)

1. **Ownership**: "Describe a time a mission-critical campaign failed during live hours. How did you communicate the downtime to the sales team, and how did you resolve it?"
2. **Technical Depth**: "Walk me through your process for auditing webhook completeness. How do you know if 100% of the call data actually made it into the CRM?"
3. **Optimization**: "If our connect rate drops by 15% on a Tuesday morning, what are the first three things you check in BatchData or BatchDialer?"
4. **Escalation**: "When do you decide to stop a campaign versus trying to fix it while it's running? Give me a specific example of a 'kill' threshold."
5. **Tools**: "Compare Retell AI and Vapi based on your experience. Which is more resilient for high-volume outbound, and why?"

## 5) Candidate Sourcing Run (Week-2)

- **Channels**: Indeed, ZipRecruiter, Ops Facebook groups.
- **Top of Funnel Target**: 60 applicants.
- **Candidates Sourced**: 8 (Initial batch).
- **Candidates Shortlisted for Screen**: 5.

## 6) Initial Candidate Slate and Screen Schedule

| Candidate | Source | Stage | Scheduled time (UTC) | Notes |
|---|---|---|---|---|
| Kevin Tran | Indeed | Offer Accepted | 2026-04-23 09:00 | **HIRED**. Expert AI Dialer Ops. |
| Amanda Smith | ZipRecruiter | Screen Completed | 2026-04-23 10:30 | **FAIL**. Basic dialer exp only. |
| Robert Jones | FB Group | Final Interview | 2026-04-24 09:00 | **KEEP AS BACKUP**. Strong #2. |
| Linda Wang | LinkedIn | Exercise Passed | 2026-04-25 10:30 | **STRONG TECH**. Backup. |
| Mark Thompson | Indeed | Exercise Assigned | 2026-04-25 12:00 | Backup. |

## 8) Technical Exercise Results (April 28)

### Kevin Tran
- **Diagnosis**: 5/5. Identified 401 Unauthorized in 2 minutes. Linked it to token expiry on the webhook receiver side.
- **Resolution Plan**: 5/5. Recommended checking CRM middleware secrets and auditing the Retell API key. Proactively suggested a retry strategy with alert throttling.
- **Tools Knowledge**: 5/5. Deep experience with Retell AI webhooks and BatchDialer API limits.
- **Verdict**: Move to Final Interview (Lead Candidate).

### Robert Jones
- **Diagnosis**: 4/5. Correctly identified the auth failure but didn't immediately link it to the webhook receiver secret.
- **Resolution Plan**: 4/5. Good focus on auditing logs.
- **Tools Knowledge**: 4/5. Strong in BatchData lead hygiene.
- **Verdict**: Move to Final Interview (Strong Technical #2).

## 10) Final Interview Results (May 1)

### Kevin Tran
- **Ownership**: 5/5. Described a critical Retell AI API outage and how he manually bridged the data to ensure no lead leakage.
- **Technical Depth**: 5/5. Deep understanding of webhook payloads and how to audit them for 100% data integrity.
- **Optimization**: 5/5. Suggested 3 specific list-tuning strategies for DFW time blocks.
- **Verdict**: **OFFER RECOMMENDED**.

### Robert Jones
- **Ownership**: 4/5. Good accountability.
- **Technical Depth**: 4/5. Solid, but slightly less depth on API troubleshooting than Kevin.
- **Verdict**: **BACKUP**.

## 11) Offer Decision (May 4)

- **Selected Candidate**: Kevin Tran
- **Offer Terms**: 
    - Base: $60,000
    - Bonus: $5,000 annual for maintaining 98%+ system uptime
- **Status**: **Offer Accepted**.
- **Start Date**: May 11, 2026.

## 12) Delivery Timeline

- **Open Sourcing**: April 21 (Done)
- **Complete Initial Screens**: April 24 (Done)
- **Practical Exercises Reviewed**: April 28 (Done)
- **Final Interviews**: May 1 (Done)
- **First Offer Issued**: May 4 (Done)

