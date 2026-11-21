# WholesaleOS streamlining plan

## Get to a new seller inquiry from a phone

The seller inquiry is saved. The Facebook intake writes `facebook_lead_ad`, while the **Facebook Ad** filter matches only `facebook_ad`. I checked the saved record against that filter and confirmed it is excluded. The screenshot also shows five stacked filters, an AI call batch control, and a wide table before any lead details. The current layout reserves space for the desktop sidebar even on a narrow screen.

**Workaround on the previous release.** On **Leads**, change **Facebook Ad** to **All Sources**, then search the seller’s first name. The link in the owner email also opens the record directly.

## Proposed rollout

| Priority | Timing after approval | What changes |
| --- | --- | --- |
| 1. Find every Facebook lead | Same day | Make the **Facebook Ad** filter include both saved Facebook source values and give both a consistent label. Keep the original source values on existing records. Add **Clear filters** to the empty state and make **Newest first** easy to choose. |
| 2. Make Leads usable on a phone | Next business day | Put search and **Filters** above a list of tappable lead cards. Show the seller name first, then source, received time, status and next action. Show **Address pending** when the form has no address. Put import, export, retention and batch-call controls behind their own menus. Use a collapsible mobile navigation drawer and keep the desktop table. |
| 3. Give operators a follow-up queue | Next 2–3 business days | Add **New Inquiries** and **My Follow-ups** entry points that open the same lead record. Show the assigned owner, due date, last contact and next action. Let the operator log a manual email, record the response, reschedule follow-up or close the task with an outcome. Use the existing lead and task records as the source of truth. |

**Search behavior.** Support first or last name, full name, email, formatted or unformatted phone, and address. Count and sort matches across the full list. Keep active filters visible so the operator can see why a search might exclude a lead. Preserve the existing direct links from owner email and in-app alerts.

## Acceptance checks

- [x] The **Facebook Ad** filter includes both saved Facebook source values. The fixed predicate matched the known live inquiry. The browser fixture showed both Facebook variants and displayed the addressless lead by seller name and source. The regression suite checked the query for other sources.
- [ ] In signed-in iPhone Safari at 360–430 px widths, a new inquiry opens in two taps or fewer from **New Inquiries**. The list and lead details fit the screen without horizontal scrolling.
- [x] Search by name, email, phone or address is implemented. Active filters and reset are available. Regression checks cover direct lead links independent of the current list. The browser fixture exercised email search and routing from the assigned-task queue.
- [x] The browser fixture logged a manual email, set a next date, kept the task open and then closed it with an outcome. Consent review uses the existing dialogs. Production outreach checks below passed.
- [x] Regression and browser checks covered the existing desktop lead table and drawer. The hosted candidate passed the route and webhook checks before promotion. The production database still has the original lead and open task.

## Progress on November 21, 2026

- The source fix, responsive Leads view, **New Inquiries** and **My Follow-ups** are implemented in commit `4bf0c59088191e88a8587fec0634336dae26ed43` on `codex/wholesaleos-leads-workflow`. The changes use the existing lead, activity and task tables. No database migration or webhook code changes are part of this release.
- Local checks passed with 184 frontend tests, type checking, the production build and the lint gate. Chromium with fixture data verified the list at 390 px, the lead drawer at 360 px, navigation, source and email searches, direct lead and task links, manual email logging, rescheduling, task resolution and the desktop table. The fixture run made zero outreach requests.
- A read-only production check found one stored Housing Pilot submission since the campaign start, with a follow-up task. For the known inquiry, the revised source filter matched, the assigned task was pending, and the prior owner email showed delivered. Supabase had zero active outreach schedules and Vercel cron was paused. The count covers the submissions stored in WholesaleOS.
- The initial promotion request was held by automatic review after the broader test suite flagged ambiguous lead selectors. The revised regression covers both the desktop row and the mobile card. The prior serving deployment, `dpl_5VQpYmWtD5voTnJo2uQtZDi1FkgF`, is the rollback target.
- All four CI jobs passed. The staged build passed health and app-route checks, pointed at the existing production Supabase project, and rejected an unsigned Facebook event with HTTP 403. [GitHub CI](https://github.com/julysses/Wholesale-automation/actions/runs/44946024964)
- The public app now serves `dpl_CTWtVLLrUbp8cq3pqWjKyZYza8yw`. The live health route returned OK. Both app routes served the tested bundle, and the webhook still rejected an unsigned request with HTTP 403. Vercel cron was paused on the serving deployment. [Vercel deployment](https://vercel.com/julysses-projects/wholesale-automation/CTWtVLLrUbp8cq3pqWjKyZYza8yw)
- After promotion, WholesaleOS still had one recorded Housing Pilot submission, zero recorded submissions missing a follow-up task, and zero Housing Pilot SMS jobs in processing or sent status. The known inquiry still matched the Facebook filter, its assigned task was pending and the owner email retained its delivered event. Supabase still had zero active outreach schedules. No Meta settings were edited and no new test lead was submitted to the live form.

## Resume from here

Open **New Inquiries** on an iPhone signed in as an operator. Open the known Housing Pilot inquiry and confirm the width and that the follow-up task is visible. Compare the next real Meta submission with its WholesaleOS receipt, assigned task and owner alert as it arrives. The known task remains open. Leave it pending until the operator records what happened.

If the live app or intake fails after this release, use `dpl_5VQpYmWtD5voTnJo2uQtZDi1FkgF` to restore the previous Vercel deployment. Recheck the public alias, health, Facebook webhook rejection, recorded receipts and open tasks, and both outreach schedule holds. Use `4bf0c59088191e88a8587fec0634336dae26ed43` as the serving code baseline for subsequent WholesaleOS frontend changes.
