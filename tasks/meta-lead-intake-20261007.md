# Meta developer signup and lead intake — October 7, 2026

## Objective
Create the user's developer account and connect Hilltop Home Company native Facebook Lead Ads intake to WholesaleOS with signed webhooks, durable deduplication, owner assignment and consent-aware routing. No paid campaign is started by this setup.

## Current authoritative state
- User signed into Facebook for the Meta developer flow.
- Official registration page: https://developers.facebook.com/async/registration/dialog/?src=default
- Current step Register; subsequent Verify account, Contact info and About you steps are pending.
- Continue explicitly accepts Meta Platform Terms and Developer Policies. Asked the user for action-time authorization; no terms accepted yet.
- Browser tab1348645482. Preserve this exact live signup page.
- Repository checkpointa9f2256 was pushed successfully to working and production branches after the prior transient DNS failure.

## Registration and connection checklist
- [ ] User authorizes Meta terms acceptance or clicks Continue personally.
- [ ] Complete account verification; user supplies any identity/OTP checks.
- [ ] Confirm developer contact email and business/operator role.
- [ ] Create an app for the Page lead retrieval use case using current Meta setup choices.
- [ ] Confirm the exact Hilltop Home Company Page and business portfolio; do not conflate with Hilltop Homes profile.
- [ ] Inspect current supported Graph API version; tools/facebook_ads_adapter.py currently pins v19.0 and needs reconciliation.
- [ ] Configure app identity, privacy policy, data deletion path and required business verification/review.
- [ ] Configure least required Page/lead permissions and server-only credential storage. Obtain action-time confirmation if granting security-sensitive access through browser UI.
- [ ] Configure /webhooks/facebook/lead callback: GET challenge verifies configured token; POST HMAC-SHA256 checks raw body with app secret.
- [ ] Subscribe the exact Page to leadgen events.
- [ ] Native Meta test lead -> one durable receipt/lead/task -> Julio operator notification/email; replay must not duplicate.
- [ ] Confirm consent mapping. Facebook inquiry alone must not silently authorize seller SMS or AI calls.
- [ ] Verify app live/review/access status supports intended real intake before production readiness claim.

## Existing application
- config/settings.py: FACEBOOK_APP_ID, FACEBOOK_APP_SECRET, FACEBOOK_ACCESS_TOKEN, FACEBOOK_WEBHOOK_VERIFY_TOKEN, FACEBOOK_AD_ACCOUNT_ID.
- tools/facebook_ads_adapter.py: Graph retrieval, payload normalization and webhook verification.
- web/api/webhooks.py: GET/POST /webhooks/facebook/lead and inline processing.
- Credentials absent in Vercel/app_settings at the last audited checkpoint; do not write tokens into source, frontend variables, screenshots or chat.

## Remaining wider launch gates
SMS delivered and user receipt confirmed; STOP/refusal remains pending. Email delivered and duplicate reference refused; real unsubscribe/refusal remains pending. Retell account does not exist yet. Supabase backup dashboard requires sign-in; isolated restore rehearsal remains pending. Full checklist: tasks/production-acceptance-20261007.md.

## Developer account completed; app creation review pending
- User completed developer registration personally. Current My Apps initially showed No apps yet.
- Prepared app name Hilltop Lead Intake, contact julio@hilltophome.co. Selected All use cases -> Capture & manage ad leads with Marketing API.
- Business step showed No businesses available. Selected connect later; portfolio/Page ownership connection remains required before full launch.
- Requirements screen reported none currently; this may change when permissions/features are configured.
- Overview now shows the correct app name/email/use case and a final Create app button. Its text explicitly accepts Meta Platform Terms, Developer Policies and other applicable policies. Asked user for action-time authorization for app creation/credentials and agreement acceptance, or to click personally. No app created by the agent yet.
- Tab1348645482 stays at overview; screenshot meta-app-create-review.jpg in task outputs. After user confirmation, create app, verify app ID and dashboard, then business/Page settings and signed leadgen integration.
