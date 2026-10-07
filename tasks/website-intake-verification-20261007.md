# Website intake verification — October 7, 2026

Goal: both public websites create durable CRM inquiries, assigned Julio follow-up tasks and owner notifications to julio@hilltophome.co.

- [x] Pull CRM and Jays repositories before changes.
- [x] Locate gap: Jays contact/seller/buyer/financing forms open mailto drafts.
- [x] Replace all Jays mailto forms with same-site server intake and truthful confirmation.
- [x] Persist inquiry details, separate site source, manual-review state, and optional seller SMS receipt.
- [x] Apply tracked form configuration/function migration and verify service-only permissions.
- [ ] Run relevant regression checks and build; push both repositories; verify deployment.
- [ ] Submit clearly labeled controlled inquiries from both live sites; trace receipt, lead, task, app notification and signed email delivery.
- [ ] Verify signed-in CRM operator view and preserve proof screenshots.

Use only authorized owner contact 214-701-0100 / julio@hilltophome.co for tests. No real sellers. Preserve recipient restrictions and existing opt-outs. Buyer/financing/contact inquiries require manual review and do not authorize automated seller outreach.

Applied migration jays_website_intake; service_role retains EXECUTE, anon/authenticated denied. CRM suite: 366 passed (307 existing warnings). Jays lint/typecheck pass; local Turbopack cannot bind ports, webpack production build in progress. Live tests still pending.
