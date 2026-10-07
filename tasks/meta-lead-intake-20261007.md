# Meta developer signup and lead intake — October 7, 2026

## Objective
Create the user's developer account and connect Hilltop Home Company native Facebook Lead Ads intake to WholesaleOS with signed webhooks, durable deduplication, owner assignment and consent-aware routing. No paid campaign is started by this setup.

## Current authoritative state
- User completed developer registration and authorized final app creation with "yes create".
- Created Hilltop Lead Intake, app ID1028695470188549, lead-capture Marketing API use case, contact julio@hilltophome.co. Unpublished; no business available during creation, connection deferred.
- Saved privacy https://hilltophome.co/privacy-policy, terms https://hilltophome.co/terms-of-service and deletion instructions at the privacy URL. Verified published policy includes deletion request instructions and business phone.
- Meta Page webhook screen explicitly says unpublished apps receive dashboard test webhooks only, not production data, including admin/tester data. Publishing remains a real readiness gate.
- Page leadgen subscription defaults to v26.0; Graph API Explorer also v26.0. Adapter updated from v19.0. Bearer headers replace token query parameters; errors log only exception types. Three regression tests cover each Graph request path, URLs and logs. Full backend351passed,307existingwarnings; diffcheckclean.
- User approved pages_show_list/leads_retrieval token generation and Vercel storage. Completed Meta OAuth using Hilltop Homes login profile but selected ONLY current Hilltop Home Company Page1303115306222198, not future Pages. Final saved connection confirmed. Generated user token, selected distinct Hilltop Home Company Page token and stored FACEBOOK_ACCESS_TOKEN as production-only Vercel Secret; success toast and Secret row verified. No token value written into files/chat/screenshots. Redeployment still needed; expiry not yet checked.
- Graph Explorer GET me?fields=id,name returned error100: requires pages_read_engagement or Page public access feature. Do not claim identity/API verification passed just because token selection succeeded.
- Prepared next action-time approval request: pages_read_engagement and pages_manage_metadata restricted to same exact Page, plus server-only Vercel app secret and webhook verify token. pages_manage_metadata remains Add on app permissions screen; no added grant performed yet. Preserve Graph Explorer1348645503, app1348645482 and Vercel1348645459.
- pages_manage_metadata must still be configured for Page subscriptions; do not silently grant broader ad/business scopes. Actual token expiry, exact Page and portfolio identity still require verification.

## Registration and connection checklist
- [x] User authorizes Meta terms acceptance or clicks Continue personally.
- [x] Complete account verification; user supplies any identity/OTP checks.
- [x] Confirm developer contact email and business/operator role.
- [x] Create an app for the Page lead retrieval use case using current Meta setup choices.
- [ ] Confirm the exact Hilltop Home Company Page and business portfolio; do not conflate with Hilltop Homes profile.
- [x] Inspect current supported Graph API version and update adapter to v26.0; live Graph acceptance still pending.
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

## Approved webhook scopes and credential reset handoff
- User approved pages_read_engagement/pages_manage_metadata and production-only signing-secret/verification-token storage.
- Added pages_manage_metadata to app; Ready for testing verified. Completed expanded OAuth grant restricted to ONLY current Hilltop Home Company1303115306222198. New Page token selected; Graph GET me?fields=id,name successfully returned exact ID/name. Updated production FACEBOOK_ACCESS_TOKEN Secret.
- Stored FACEBOOK_WEBHOOK_VERIFY_TOKEN as production-only Secret. Submitted FACEBOOK_APP_ID1028695470188549 as production Config. FACEBOOK_APP_SECRET was initially saved as Secret, but its value accidentally appeared in a tool result during a form-state check. No secret recorded in repository; reset is required before deployment/launch.
- Opened Meta Reset control, which requests password re-entry. Asked user to complete password and credential reset personally. Current Meta app tab1348645482 is at that prompt; no replacement secret captured yet. Do not use/redeploy old signing secret. Capture new secret silently after user reset and replace Vercel value; redact all text observations before output, including Value lines.
- Browser tabs: Meta1348645482, Graph Explorer1348645503, Vercel1348645459. In-memory verification token exists in CUA; if lost, coordinate a new value in both providers. Never copy secret values into markdown or shell output.
- Still pending: token lifetime, replacement-secret storage, production redeploy, Meta GET challenge verification, leadgen app and Page subscription, dashboard/native test lead and dedup, publication/review/business ownership. No paid ad started.
- Proof: meta-webhook-secrets-configured.jpg shows secret names/scope only. This proves storage, not current-secret validity or webhook acceptance.

## Developer account completed; app creation review pending
- User completed developer registration personally. Current My Apps initially showed No apps yet.
- Prepared app name Hilltop Lead Intake, contact julio@hilltophome.co. Selected All use cases -> Capture & manage ad leads with Marketing API.
- Business step showed No businesses available. Selected connect later; portfolio/Page ownership connection remains required before full launch.
- Requirements screen reported none currently; this may change when permissions/features are configured.
- Historical review: user subsequently authorized creation; app was created and ID verified as recorded above.
- Proof screenshots: meta-app-created.jpg, meta-app-policies-saved.jpg, meta-lead-permissions-ready.jpg in task outputs. No app secret revealed, production subscription or paid ad started.
- October7 approved-token proof: meta-page-access-connected.jpg and meta-vercel-page-token-stored.jpg. Pending webhook permission proof: meta-webhook-permission-required.jpg. App remains unpublished; no real lead ingestion proof yet.
