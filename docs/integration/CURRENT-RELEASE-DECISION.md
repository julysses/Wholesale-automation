# Current release decision — October 22, 2026

Full Friday launch remains unproven. Buyer SMS is required; no buyer campaign has
been registered or approved. This is the current decision record; dated sections
in older feature documents are historical evidence.

## Verified candidate

Runtime44894b8, docs checkpoint2c32c0c, PR21 OPEN/DRAFT. All nine Linux checks passed
in run39869071876 (713). The tested head and PR merge have identical tree65af0a6.
See buyer-analysis-ci-evidence.json for exact full references and counts.
Twenty reviewed forward proposals remain unapplied. The native Facebook receipt
migration is already in production with a different server timestamp; never replay
it or the full migration directory. The live history ends at the released Facebook
receipt migration, as recorded in production-release-refresh-2026-10-22.json.

## Fresh production evidence

Read-only checks around23:05–23:10 UTC confirm production still servesa898151 at the
same READY Vercel deployment. All saved schema categories match:101 tables,
395 constraints,113 indexes,28 triggers,127 policies,17 views/view-security records,
schema/default grants and server version. All121 saved function fingerprints and
ACLs match; none added/removed/changed. These are catalog checks, not data backups.

The buyer book currently has0 buyers and0 transactions. No existing buyer history
needs conversion, and no current buyer APN conflict was found. This does not validate
the import's maximum file size/latency, future reacquisition events or source quality.
The existing unique buyer/APN index is unchanged; different purchase events on one
parcel are held for review rather than overwritten or inserted by fallback.

Database ingestion outreach is false and its trace budget is0 cents. No allowlisted
saved application boolean overrides were present. This does NOT prove effective
Vercel environment flags: environment values take precedence and remain unverified.
The database has two existing active cron jobs, launch monitoring and retention.
The Vercel configuration also contains the existing weekday SMS-nurture cron; its
effective sending gates require verification. Do not call every schedule disabled.
No provider, schedule, configuration, migration or business row was changed.

## Carrier and cost boundary

Fresh signed-in Twilio inventory still has one Verified Low Volume Mixed campaign.
Its current description and opt-in flow cover homeowners' own property inquiries,
offers, appointments and closing updates, explicitly excluding unrelated marketing.
It does not establish buyer deal-alert approval. The exact buyer wording approval
is retained separately and does not authorize cost or activation.

SMS-only number search returned no972 result at observation;817 returned DFW options
listed at$1.15/month. A concrete candidate reference is in the local launch plan,
not in public Git. None selected, reserved or purchased; availability can change.
The prior campaign form showed$10/month Marketing, and the published vetting fee was
$15. Number/usage/carrier charges/taxes and any required brand charges must be verified
at purchase/submission. This remains a planning estimate, not a final quote or an
approved spending limit. No Buy or Register action was taken.

## Required before a release approval request

- Verify effective production flags and current signed-in operator/JWT boundaries;
  resolve the existing Vercel email-verification handoff without reading OTPs.
- Complete manual buyer edit/delete and cleanup recovery review. Inspection confirms
  import cleanup loops through1000-row batches, so it is not a total1000-row cap.
  Partial deletion/lost acknowledgment remains unproven; existing tests are narrower.
- Complete production-volume/source/APN review and PropStream handoff acceptance
  within the existing cumulative$50 cap.
- Establish an approved maintenance boundary and verified restorable production backup.
  Saved-catalog local rehearsal and the existing restore project are not that proof.
- Review the exact twenty-file hashes and matching runtime, a paused deployment and
  forward-compatible recovery. Preserve all consent/suppression/unknown receipts.

After that concrete release review, publish and verify approved buyer pages and the
business-site cross-link; obtain the final scoped registration/sender cost approval;
submit the buyer program; verify actual approval/configuration; prove fresh controlled
handset delivery, reply, STOP and operator inbox receipt. Broad sending remains a
separate result review. Twilio's current10–15-day review estimate cannot support a
promise that a newly submitted campaign will be ready FridayOctober23.
