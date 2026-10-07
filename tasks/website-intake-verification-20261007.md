# Website intake verification — October 7, 2026

Goal: both public websites create durable CRM inquiries, assigned Julio follow-up tasks and owner notifications to julio@hilltophome.co.

- [x] Pull CRM and Jays repositories before changes.
- [x] Locate gap: Jays contact/seller/buyer/financing forms open mailto drafts.
- [x] Replace all Jays mailto forms with same-site server intake and truthful confirmation.
- [x] Persist inquiry details, separate site source, manual-review state, and optional seller SMS receipt.
- [x] Apply tracked form configuration/function migration and verify service-only permissions.
- [x] Run relevant regression checks and build; push both repositories; verify deployment.
- [x] Submit clearly labeled controlled inquiries from both live sites; trace receipt, lead, task, app notification and signed email delivery.
- [x] Verify signed-in CRM operator view and preserve proof screenshots.

Use only authorized owner contact 214-701-0100 / julio@hilltophome.co for tests. No real sellers. Preserve recipient restrictions and existing opt-outs. Buyer/financing/contact inquiries require manual review and do not authorize automated seller outreach.

Applied migration jays_website_intake; service_role retains EXECUTE, anon/authenticated denied. CRM suite: 366 passed (307 existing warnings). Jays lint/typecheck pass; local Turbopack cannot bind ports, webpack production build in progress. Live tests still pending.

## Completed acceptance — 3:51 PM Central

- CRM production face1c3, Vercel dpl_Ehn97MbgqHNK1dkAX2tPYLKtQBdn READY.
- Jays website production 81d973a, Netlify deploy 6ac6af7bdc2114000842f647 Published from main. All four forms now submit to /api/intake, which waits for durable CRM success. All confirmation screens observed.
- Jays lint/typecheck and webpack production build pass; 9 server-route tests pass. Netlify production Turbopack build also published successfully. React component checklist reviewed: hooks unconditional, labeled inputs, disabled submission fieldset, accessible success/error state, no browser database credentials.
- Supabase migration reconciled against the live function before apply. Service-only EXECUTE verified; transaction rollback assertions verified notes, AI pause, configured owner, exactly one task, and idempotent repeat finalization. First rollback fixture lacked required city and failed harmlessly; corrected fixture passed and no rows retained.

| Live form | Lead ID | Durable submission ID | Owner email ID | Signed delivered UTC |
|---|---|---|---|---|
| hilltophome.co/get-an-offer | 3754dfed-0791-47b5-9fb4-2e989536930f | 23b5dd57-6cd9-4516-80d7-6f1c15524eee | a2b288e1-4f89-5c0c-ab8e-aefc74b76504 | 20:47:27 |
| thejaysdallas.com/contact (email-only) | f21ab07d-1b2b-4bab-baee-a3967ecfbf93 | df0d1d92-a330-44b5-bbb9-953d24cd7bdd | e89b3515-2f92-50d7-a012-1ab635faffc7 | 20:47:32 |
| thejaysdallas.com/sell | 4e875b1f-6098-4b3f-b3b3-7ad4f6840b93 | 82116394-8094-4797-a8b5-219a66e31b53 | 94038d88-861a-544a-8ffd-f05174ebf875 | 20:48:21 |
| thejaysdallas.com/buyers | 4f6df7d1-ffa0-4dda-842a-f930e432e2b0 | a1081da7-5eb2-48a5-87eb-8e7da0ab3fa6 | 64caad05-1aa1-5c56-bb2b-21fb3ece0c2a | 20:48:52 |
| thejaysdallas.com/financing | b1fb433e-592a-442e-a5bb-62b5c6ff5083 | 681d5d7d-8527-4fe4-b420-69e5e77e7116 | e47b491d-7625-5443-8492-14bdd9c7f30f | 20:49:22 |

Each live submission processed, one task assigned to Julio89f3b3f6-5a88-4b79-b3f4-461e0cd626a2, one durable intake notification, and one owner email accepted/delivered to julio@hilltophome.co. Both websites' inquiry notifications and delivered receipts visible in signed-in CRM. Jays contact details and full message visible in Internal Notes and qualification summary. Four Jays inquiry rows observed together in CRM. Hilltop row separately observed. SMS consent false on all five; AI paused and sequences false. Test-only follow-up tasks completed after QA; leads/receipts retained for audit. No real seller contacted.

Owner alerts include site/form source, contact email/phone, inquiry type and details, and CRM link. User inbox confirmation requested asynchronously; provider delivery is confirmed, human receipt pending response. Alerts operate independently of optional seller SMS. Recipient allowlists and prior opt-outs preserved.

Proof in task outputs: hilltop-intake-verified-20261007.jpg, jays-contact-verified-20261007.jpg, jays-seller-consent-20261007.jpg, websites-crm-notifications-20261007.jpg, jays-crm-contact-details-20261007.jpg.

## Resume scope
The specific two-website intake/CRM/owner-notification objective is verified. The older goal "finish the remaining set up and proof for production ready" remains incomplete; Retell and broader live-launch gates are outside this completed intake checkpoint. Do not mark full automation production-ready. Keep both test recipient restrictions until separate approval/acceptance.
