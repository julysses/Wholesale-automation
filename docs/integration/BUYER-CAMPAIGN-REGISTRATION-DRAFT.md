October22 late refresh: the one-campaign inventory and homeowner-only description
were rechecked unchanged. SMS-only972 search returned no results;817 returned DFW
local numbers listed at$1.15/month. No Buy/Register action, reservation, purchase or
configuration change occurred. Candidate reference retained in local launch plan;
availability and final costs are not guaranteed. See CURRENT-RELEASE-DECISION.md.

# Buyer deal-alert campaign — registration preparation, October 22

Status: draft only; not submitted, purchased, registered or enabled. This preserves
the existing homeowner campaign. The user REQUIRES buyer SMS at launch.

## Registration readiness finding

Read directly from the signed-in Twilio console on October 22, 2026:

- Registered brand: The Jays Dallas, LLC, [provider reference retained in local launch plan].
- The All-status campaign inventory contains one campaign:
  [provider reference retained in local launch plan], external ID [retained locally], Verified, Low Volume Mixed.
- Connected service: [provider reference retained in local launch plan].
- Registered connected number: [registered sender retained locally], [provider reference retained in local launch plan].
- Campaign description and opt-in flow limit texts to homeowners' own property
  inquiries, offers, appointments and closing updates, with no unrelated marketing.
  Opt-in is the optional unchecked Hilltop offer-form checkbox; this is NOT buyer
  deal-alert consent. Advanced Opt-Out is applied. Standard STOP variants are
  registered; HELP/INFO are registered. START never clears CRM suppression.
- Existing service inbound URL: wholesale-automation.vercel.app/webhooks/twilio/inbound.
- Current policy references shown in the campaign:
  https://thejaysdallas.com/privacy-policy and https://thejaysdallas.com/terms.
  These references alone do not establish that the pages cover buyer marketing.
- New-registration form offers Marketing at $10/month, and Low Volume Mixed at
  $1.50/month. Dedicated buyer deal promotions fit the Marketing description;
  do not choose an unrelated use case solely for price. No choice was submitted.
- The unsubmitted registration modal was closed; the one-campaign inventory was
  verified unchanged. No sender, service, campaign, opt-out or routing was edited.

Authenticated account references are retained in the local launch plan.
Public documentation: https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/quickstart

## Timing and fees

The [current Twilio quickstart](https://www.twilio.com/docs/messaging/compliance/a2p-10dlc/quickstart)
says reviews take 10–15 days. The [help FAQ](https://help.twilio.com/hc/en-us/articles/11587910480155-A2P-10DLC-Campaign-Vetting-FAQ)
shows a different estimate (up to five business days), so these pages do not
establish an exact completion date. Neither supports a promise of next-day approval.
The FAQ states a $15 verification fee. The registration form shows the Marketing
recurring fee of $10/month. Number, usage, carrier fees and taxes remain to price.
A new recurring purchase requires the user's concrete approval before submission;
no payment or campaign creation has been authorized/executed at this checkpoint.

## Proposed registration copy — verify the real flow before submission

Brand: The Jays Dallas, LLC, doing business as Hilltop Home Co.
Program: Hilltop Home Co. Buyer Deal Alerts.
Use case: Marketing, subject to provider validation.
Service: a separate service for buyer deal alerts; preserve the existing homeowner
service/number and inbound behavior. A suitable sending number and full cost remain
unselected. Do not move the registered homeowner number to the new campaign.

Proposed campaign description:

The Jays Dallas, LLC, doing business as Hilltop Home Co., sends recurring automated
marketing texts about wholesale property opportunities to real estate buyers who
have separately provided written consent to the Buyer Deal Alerts program.
Messages describe available properties, asking prices, showing opportunities and
availability updates. No purchased-list enrollment, homeowner-inquiry enrollment,
lending, debt relief or AI-call consent is included. Recipients may opt out at any
time with STOP or obtain support with HELP.

Proposed sample 1:

Hilltop Home Co. (The Jays Dallas, LLC): You requested Buyer Deal Alerts. Dallas
3-bed/2-bath opportunity, asking $185,000. Reply for details. Msg frequency varies;
msg & data rates may apply. Reply STOP to opt out or HELP for help.

Proposed sample 2:

Hilltop Home Co. Buyer Deal Alerts: A property matching your Dallas buy box is
available. Reply DETAILS to request information or call (214) 701-0100. Reply STOP
to opt out or HELP for help.

Proposed sample 3:

Hilltop Home Co. Buyer Deal Alerts: The property you requested is no longer
available. We'll send other opportunities only while you're enrolled. Reply STOP
to opt out or HELP for help.

Do not list keyword enrollment; replying START must not enroll someone without
new reviewed buyer-specific consent or automatically clear CRM DNC.

Owner-approved written disclosure (October 22, 2026):

I agree to receive recurring automated marketing text messages from Hilltop Home Co. (The Jays Dallas, LLC) about wholesale property opportunities and Buyer Deal Alerts at the mobile number I provide. Message frequency varies. Message and data rates may apply. Reply STOP to opt out or HELP for help. Consent is not a condition of purchase. The Buyer SMS Terms and Privacy Statement are available beside this optional choice.

Exact version: `7d063db412e8c02a7de1d048b8604bcc775b987be84e9e7fdcda304bcc2738be`. The complete approved privacy/terms and
identity/support are retained in BUYER-SMS-APPROVED-WORDING.md; any changed copy
requires a new exact version review. Approval is wording only, not fees or sending.

The checkbox must begin unchecked and remain optional. The reviewed source must
retain the exact text, choice, phone, timestamp and affirmative action. Existing
contact information and homeowner-inquiry consent never enroll a buyer.

## Not ready to submit — required missing facts

1. A published buyer-specific enrollment/evidence page or actual retained signed
   buyer-consent artifact with a publicly reviewable blank copy. Do not assert a
   buyer form exists or invent a live URL. The candidate review screen is for
   administrators; it is not the consumer opt-in form and never proves phone ownership.
2. Published policy/terms coverage for buyer marketing, program name/frequency,
   HELP/STOP, support and mobile consent privacy; verify actual pages before using.
3. Accepted sender/service/number plan, priced total and explicit purchase approval.
4. Dedicated transport and signed callbacks/replies/suppression now pass local
   synthetic acceptance (BUYER-SMS-TRANSPORT.md). Still verify actual sender
   configuration, consumer enrollment and truthful registration message-flow text.
5. Provider approval/registered number, controlled handset delivery/reply/STOP,
   operator acceptance and reviewed production release/rollback.

Do not submit this draft as a statement that the missing workflow is live. Keep
buyer SMS REQUIRED / NOT ACCEPTED; broad sending and schedules remain paused.

Current candidate update: invitation-based consumer enrollment and separate buyer
policy pages are now implemented, but remain unpublished/disabled and their exact
wording was approved by the owner on October 22. Registration must describe this actual invitation,
optional choice and administrator review flow once it is live; do not claim that
consumer enrollment is already available or submit an invented public proof URL.
See BUYER-ENROLLMENT.md. No registration or purchase was performed.

Candidate message-flow description for verification before registration:

An administrator creates a seven-day, one-use private enrollment link after a
buyer requests enrollment. The app does not send that link. The buyer enters the
number bound to the invitation and makes an optional, initially unchecked choice
beside the exact buyer disclosure and public privacy/terms links. The app retains
the choice, exact program version and immutable receipt. A positive choice creates
an assigned administrator review task; it does not immediately enable messaging.
An approved administrator reviews the retained evidence before SMS eligibility.
A refusal disables buyer SMS immediately and existing DNC is never cleared.
This flow does not prove phone ownership. Submit this description only after the
actual published flow and proof links have been verified.

October 22 read-only pricing follow-up: the signed-in number search lists US local
SMS-capable numbers at $1.15/month. Searches restricted to SMS in area codes 214
and 469 returned no results at that moment. No number was selected or purchased;
availability must be refreshed before choosing the dedicated sender. Public
[US SMS pricing](https://www.twilio.com/en-us/sms/pricing/us) lists $0.0083 per
outbound/inbound SMS segment, plus carrier fees; Unicode/multipart messages may
consume multiple segments. Together with the previously observed Marketing fee,
base recurring cost is $11.15/month before usage/carrier fees/taxes, plus the $15
campaign vetting fee. This is a planning subtotal, not a final checkout quote or
purchase authorization. Current account-specific taxes, any extra registration
charges, actual selected number and total cap still require concrete review.
