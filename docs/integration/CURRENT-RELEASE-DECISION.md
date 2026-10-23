Cloud follow-up VERIFIED: all9 jobs of run719/39875339193 succeeded for
cf4dd50441688aacbd1f88fd16762c42f66751be. Buyer job logs prove the dedicated
maximum CSV import/lock assertions ran on LinuxPG17.11. Head and tested PR merge
have identical Git trees. See buyer-import-linux-ci-evidence.json. Prior717 has
canceled jobs and is not a full pass. This changes software evidence only;
all21 migrations remain unapplied and live launch gates remain open.

Latest follow-up: maximum buyer CSV imports and bounded lock refusal/retry pass
locally, with both5000-row extremes and all10 intake journeys. See
BUYER-IMPORT-VOLUME.md. The dedicated Linux job must include `--buyer-import`;
run717 predates that workflow wiring and cannot certify those new assertions.
The application runtime/migration SQL remain unchanged frombd30ba0.
Existing CLI control-plane authentication works, but passwordless linked dumping
creates a write-capable temporary login; this was inspected, not executed.
See PRODUCTION-BACKUP-READINESS.md. No current export/restore is certified.
The exact Twilio inquiry is submitted to its automated Help Center; human ticket
routing awaits additional approval. Generated answers are not carrier approval
or a complete quote. See TWILIO-SUPPORT-INQUIRY-STATUS.md.

Current backup follow-up at23:42 UTC: eight completed daily physical backups are
listed, latestOctober22 12:13:03 UTC; the olderOctober8 restore is markedcompleted.
Today's restore is unverified, PITR is not enabled and Storage counts are0/0. Native
clones can auto-start copied jobs, so isolation must be reviewed first. The provider's
API Gateway incident is Monitoring and includesus-west-2; public app health returned
200 with its constant process-only response. See PRODUCTION-BACKUP-READINESS.md and
production-backup-observation-2026-10-22.json. No restore/purchase/config change.

Current candidate runtimebd30ba0 passed all9 jobs in run39872079323 (715), with
identical head/PR-merge Git trees; see buyer-mutation-ci-evidence.json. All21
proposals remain unapplied. Single-buyer form edits/deletes now have retained
recovery and contact-bound consent safeguards. Final local full rehearsal passes
10 synthetic intake journeys123.02s. This is software candidate verification;
production/operator/provider/backup/carrier acceptance remains open.

# Current release decision — October 22, 2026

Full Friday launch remains unproven. Buyer SMS is required; no buyer campaign has
been registered or approved. This is the current decision record; dated sections
in older feature documents are historical evidence.

## Previously verified analysis candidate

Runtime44894b8, docs checkpoint2c32c0c, PR21 OPEN/DRAFT. All nine Linux checks passed
in run39869071876 (713). The tested head and PR merge have identical tree65af0a6.
See buyer-analysis-ci-evidence.json for exact full references and counts.
Twenty-one reviewed forward proposals remain unapplied. The native Facebook receipt
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
- Single-buyer form edit/delete recovery is implemented and verified locally; current
  remote CI passes; signed-in acceptance remains to be confirmed. Import cleanup/other
  legacy editor recovery review remains separate. Inspection confirms
  import cleanup loops through1000-row batches, so it is not a total1000-row cap.
  Partial deletion/lost acknowledgment remains unproven; existing tests are narrower.
- Complete production-volume/source/APN review and PropStream handoff acceptance
  within the existing cumulative$50 cap.
- Establish an approved maintenance boundary and verified restorable production backup.
  Saved-catalog local rehearsal and the existing restore project are not that proof.
- Review the exact twenty-one-file hashes and matching runtime, a paused deployment and
  forward-compatible recovery. Preserve all consent/suppression/unknown receipts.

After that concrete release review, publish and verify approved buyer pages and the
business-site cross-link; obtain the final scoped registration/sender cost approval;
submit the buyer program; verify actual approval/configuration; prove fresh controlled
handset delivery, reply, STOP and operator inbox receipt. Broad sending remains a
separate result review. Twilio's current10–15-day review estimate cannot support a
promise that a newly submitted campaign will be ready FridayOctober23.
