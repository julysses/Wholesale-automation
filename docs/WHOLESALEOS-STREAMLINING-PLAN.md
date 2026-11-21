# WholesaleOS streamlining plan

## Get to a new seller inquiry from a phone

The seller inquiry is saved. The Facebook intake writes `facebook_lead_ad`, while the **Facebook Ad** filter matches only `facebook_ad`. I checked the saved record against that filter and confirmed it is excluded. The screenshot also shows five stacked filters, an AI call batch control, and a wide table before any lead details. The current layout reserves space for the desktop sidebar even on a narrow screen.

**Today’s workaround.** On **Leads**, change **Facebook Ad** to **All Sources**, then search the seller’s first name. The link in the owner email also opens the record directly.

## Proposed rollout

| Priority | Timing after approval | What changes |
| --- | --- | --- |
| 1. Find every Facebook lead | Same day | Make the **Facebook Ad** filter include both saved Facebook source values and give both a consistent label. Keep the original source values on existing records. Add **Clear filters** to the empty state and make **Newest first** easy to choose. |
| 2. Make Leads usable on a phone | Next business day | Put search and **Filters** above a list of tappable lead cards. Show the seller name first, then source, received time, status and next action. Show **Address pending** when the form has no address. Put import, export, retention and batch-call controls behind their own menus. Use a collapsible mobile navigation drawer and keep the desktop table. |
| 3. Give operators a follow-up queue | Next 2–3 business days | Add **New Inquiries** and **My Follow-ups** entry points that open the same lead record. Show the assigned owner, due date, last contact and next action. Let the operator log a manual email, record the response, reschedule follow-up or close the task with an outcome. Use the existing lead and task records as the source of truth. |

**Search behavior.** Support first or last name, full name, email, formatted or unformatted phone, and address. Count and sort matches across the full list. Keep active filters visible so the operator can see why a search might exclude a lead. Preserve the existing direct links from owner email and in-app alerts.

## Acceptance checks

- [ ] The **Facebook Ad** filter returns both a newly received native form lead and an older Facebook record. A lead with no address appears by seller name and source. Other source filters still return the correct records.
- [ ] In signed-in iPhone Safari at 360–430 px widths, a new inquiry opens in two taps or fewer from **New Inquiries**. The list and lead details fit the screen without horizontal scrolling.
- [ ] An operator can find a lead by name, email, phone or address. An empty result explains the active filters and offers a one-tap reset. An owner-alert link opens the right record regardless of current filters.
- [ ] An operator can log a manual email and set a next date on the same follow-up task. The task stays open and visible until the operator records an outcome. SMS and AI-call consent remain visible and automated seller outreach stays off.
- [ ] Desktop sorting, pagination, lead editing and existing deep links still work. Verify the source fix in preview first, then check the published filter with the existing record without resending any seller communication.

The first release is targeted at the Leads screen and needs no data migration. The estimates assume the current serving release remains the baseline and a signed-in operator is available for mobile acceptance. This plan has been recorded in Git. Implementation and deployment are pending.
