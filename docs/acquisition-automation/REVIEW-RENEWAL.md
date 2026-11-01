# Review renewal implementation contract

Status: request/receipt validation and a local additive lineage migration; full upgrade verification is running. No renewal endpoint, controlled renewal writer, policy or activation exists yet. This document keeps the full lifecycle objective open and replaces the unsafe shortcut of extending an old approval's expiry.

## Observed current implementation

The canonical contract remains `deals`; immutable terms remain `acquisition_contract_versions`; review decisions and withdrawals remain `acquisition_contract_reviews`; lifecycle handoffs remain `acquisition_contract_transitions`. No second CRM or parallel review ledger is needed.

Current definitions in `20261101085535_acquisition_disposition_contract_transition.sql` require the exact approved review to be the latest decision, unexpired, and supported by current membership/session, reviewer policy and evidence. Recorded execution, title entry and disposition handoff retain exact review IDs. The title/disposition predicates and writers compare their expiry directly against earlier review rows. `20261101050425_acquisition_execution_deadline_authority.sql` derives calendar-date authority from exact deadline review IDs embedded in execution findings. Source journals retain exact artifact/version/hash/verification identities, and their currentness checks require retained references and current verification/scanner authority.

Consequently, simply inserting another ordinary execution approval breaks the original handoff reference; updating original expiry changes history; relaxing latest-review checks can revive superseded decisions; widening allowed stages alone leaves stale evidence and dependency expirations unresolved. None is the implementation.

## Operator flow

Within the existing numbered contract-review step:

1. Show which original review expired or needs fresh evidence, the affected dependencies and the next review required.
2. Refresh evidence verification for the same immutable original bytes, using approved scanner/retention controls. A new document, changed terms, changed title facts or changed purchase path requires its own reviewed amendment or replacement workflow.
3. Show original findings and current source/policy/dependency context for personal review. Require an explicit confirmation and note; renewal cannot be scheduled or performed by AI.
4. Append the new review linked to the original and immediately preceding review. Preserve exact request recovery and parent navigation holds.
5. Reassess downstream reviews independently. Renewing a deadline or execution review does not automatically renew title or disposition. A historical saved receipt never grants current approval or transaction authority.

Withdrawals remain independent of renewal and may be recorded while acquisition is paused. Renewal is unavailable while paused, after withdrawal or supersession, or in closed/cancelled/expired/disputed states. A withdrawn decision requires a distinct new review/remediation path; renewal must not silently undo it.

## Additive storage approach

Extend the existing review ledger with nullable original-root and immediate-predecessor references for renewed approved rows. Historical rows keep null lineage. Before writing SQL, inventory the latest disposable catalog, constraints, indexes, RLS, grants, triggers and migration history; record the entity mapping and conflicts.

Use exact composite references to bind workspace, contract, immutable version, review kind and deadline term where applicable. The root is an original approved review with no renewal parent. A renewed row has a new ID; its root and predecessor remain immutable. The writer must derive and validate lineage, disallow cycles/forks, and serialize on the existing contract/review locks and expected sequence. Do not rely on a client-supplied root or fingerprint as authority.

Deadline sequence is shared across date terms, while predecessor/root selection is specific to the selected term. A later review of another term must advance the expected stream sequence without replacing this term's predecessor. Other review kinds use their existing sequence semantics.

New findings on a different root supersede prior authority. An original root that was superseded cannot become current merely because its immutable row still says approved. Withdrawal of the latest applicable decision invalidates that chain. Historical transitions always retain their original root IDs.

Compensation: pause acquisition or revoke applicable policy, retain all original and renewal rows/audits, and keep renewed authority unavailable until a forward-only correction. Never delete or rewrite original decisions to roll back.

## Verified disposable catalog (November 1)

Reproducible inventory: `scripts/acquisition_review_renewal_inventory.py`, run through the offline test launcher. Evidence: `evidence/2026-11-01-review-renewal-local-catalog.json`. The `DispositionTransitionChoiceTests` fixture reaches migration `20261101090156`; the embedded 102-entry manifest is a reference, not a claim that this inventory reruns the populated full upgrade. No production connection.

The five existing entities (`deals`, contract versions, reviews, transitions and disposition plans) expose139 columns,83 constraints,22 indexes,10 policies and5 application triggers. All five have RLS enabled. Review grants allow authenticated SELECT only; no anonymous/service-role grant or client write grant exists. The immutable review trigger is present. The inventory verifies these controls before saving evidence.

Storage conflicts to resolve in the additive migration:

- Existing `deadline_original_review_id`, `title_original_review_id` and `disposition_original_review_id` identify withdrawal targets. Approved rows must keep those null under current shape checks. Do not reuse them for renewal lineage.
- Existing generic review identity omits kind/status; deadline identity includes nullable date term. A generic composite foreign key containing nullable date term would skip validation for other kinds. Use a non-null normalized stream discriminator (or separate complete references) so every renewal enforces scope, kind, date term and approved status.
- Preserve the unique workspace/contract/version/kind/sequence stream, including the shared sequence across deadline terms. A lineage chain's immediate predecessor must be earlier and in the same term/root; a unique predecessor can reject forks but does not establish current authority or prevent revival after an intervening withdrawal.
- Existing immutable triggers cover UPDATE/DELETE only. A new insert guard must validate original root, predecessor and unchanged facts under the writer's existing serialization; client grants must remain SELECT-only. Historic rows must retain null lineage without backfilling or rewriting approvals.
- Existing transition references and title/disposition source journals bind original approval IDs. Storage alone must not make renewal available; resolver and writer integration remain required before any API activation.

Inventory verification passed in5.063s; `/tmp/review-renewal-inventory-final.log`. Full populated upgrade, new lineage constraints and concurrency testing remain pending because no renewal migration has been authored yet.

## Current authority resolution

Implement a private resolver separating historical identity from current supporting review:

- Given the exact original root and time, derive the latest applicable chain member under workspace/version/kind/term scope. Reject missing, branched, superseded, withdrawn or invalid lineage.
- Return the effective review identity, bounded expiry and dependency/source snapshot only after the full current checks. The original root's immutable expiry is historical; never mutate it.
- Renewed facts must match the root: executed contract and terms, deadline calendar date/interpretation, title findings/report cutoff, disposition proposal/exit and cited original content. Verification/session/policy snapshots may be freshly derived only through their existing approved controls. New bytes, changed material findings or a different deal structure are not renewal.
- Resolve deadline roots before execution, execution before title, and title before disposition. Preserve existing originals and explicit dependency IDs; compare effective dependency identity/expiry using the resolver rather than old row expiry. Every dependent review still needs its own fresh human decision when expired or its bound snapshot changed.
- Refresh evidence journals from the same retained artifact/version/hash. A new scan does not edit an older journal. Current scan, retention, signer scope, reviewer membership/session and policy snapshots must all be checked again.
- Keep exact actor/session/request fingerprint recovery ahead of fresh activation checks. Receipt replay remains historical even when renewal authority subsequently expires or is withdrawn.

Update every affected resolver, lock helper, source admission, current predicate, candidate and writer together. In particular audit direct `.expires_at` reads and exact `.verification_id` comparisons in deadline, execution, title and disposition code. A partial resolver update must remain unavailable to live callers.

## Request and receipt

`schemas/acquisition_review_renewal.py` defines a strict frozen request and historical receipt for the forthcoming controlled writer. The request identifies kind/date term, immutable contract version, expected stream sequence, root and predecessor, selected policy, requested expiry, personal review and exact note. A server-derived discovery fingerprint binds displayed originals, current scans/policies and exact dependency reviews. It is a precondition, not proof of authorization.

The request cannot supply replacement findings, sources, actor, original expiry, policy snapshots or execution authority. The writer must rederive the fingerprint under locks, compare it to the displayed snapshot, then recheck expiry immediately before insert. ISO timezone-aware timestamps are syntax only; the mounted API/writer must enforce freshness and all policy/source/dependency caps.

A receipt confirms only the exact new review and sequence, root/predecessor, tenant, contract, kind and date term. `approval_current` and `execution_authorized` remain false. The client must perform a separate fresh state read.

## Delivery and acceptance work remaining

- [x] Inspect current source dependencies and document the lineage/expiry problem.
- [x] Define strict non-executing renewal request/receipt validation and rejection tests.
- [ ] Disposable catalog inventory and additive lineage storage/constraints/RLS tests.
- [ ] Private lineage resolver, per-kind fact identity and dependency expiry integration.
- [ ] Same-byte evidence refresh at supported stages without enabling new agreement uploads or silently replacing sources.
- [ ] Controlled human renewal writer, fresh policy checks, sorted combined locks and immutable audit.
- [ ] Current read/choice API with fingerprint binding and bounded projections.
- [ ] Guided UI with original facts, dependencies, explicit confirmation and exact retry/reload recovery.
- [ ] SQL concurrency, post-wait expiry/revocation and tenant/role/MFA/session tests; deadline shared-sequence tests.
- [ ] Prove withdrawn/superseded/cross-root chains cannot revive; changed facts route to separate review; original transitions and historical receipts remain intact.
- [ ] Full populated-upgrade and real gateway journey, frontend/backend checks and desktop/phone QA.
- [ ] Push only after predecessor CI completes; confirm exact successor. Hosted/legal/provider release approvals remain separate.

This work does not complete buyer matching, disclosure delivery, distribution approvals, deposits, closing, exception states, remaining acquisition channels or hosted acceptance. Those PRD requirements remain in the overall plan.

## Local lineage implementation (candidate128)

CLI-created `20261101093742_acquisition_review_renewal_lineage.sql` adds separate root/predecessor IDs, a non-null generated stream discriminator, scoped approved-parent foreign keys, unique predecessor and root-chain indexes. A private INSERT trigger locks the canonical deal, requires the latest applicable predecessor and next shared stream sequence, verifies an original approved root and unchanged material findings/artifact identity. It preserves existing null-lineage rows, withdrawal fields, RLS, grants and immutable UPDATE/DELETE protection. No callable renewal writer or current-authority resolver is added.

The trigger computes source version from its base columns because generated columns are not populated in a BEFORE INSERT trigger. Initial focused testing found this issue; corrected before the four-case pass. Two initial test argument mistakes were also corrected. Four focused cases passed26.639s (`/tmp/review-renewal-storage-final.log`): valid chained append/history preservation, fork/scope/partial-lineage/changed-findings rejection, withdrawn/superseded rejection and client-write denial. The added all-kind/shared-date-sequence case is running separately.

Manifest now includes103 migrations and full-catalog workflows include five renewal storage cases. Full populated schema/access/application/API rehearsal runs as session43336 in `/tmp/review-renewal-lineage-upgrade.log`; do not restart while live. All-kind focused session28729 is `/tmp/review-renewal-all-kinds.log`. Neither is yet claimed passed. No production apply. The controlled writer still must enforce fresh membership/session, policy/evidence/activation/dependencies and current expiry under combined locks; storage links alone are not authorization.

Final focused result: all five storage cases passed37.170s, session96401 terminal0 (`/tmp/review-renewal-storage-five.log`), including all supported kinds/shared deadline sequence. Full rehearsal43336 remains running and is not yet passed.

Candidate128 verification history: all-kind session28729 finished1 due to an omitted test-method boundary that inadvertently ran fixture setup twice after the all-kind assertions. Restored the separate client-denial method; then launched final five-case session96401 (now passed) in `/tmp/review-renewal-storage-five.log`. Full upgrade43336 remains live and may have imported the earlier test definition; do not restart it until terminal, and do not treat it as final coverage of the corrected five-case suite. The SQL migration did not change after its four-case pass.

## Private chain identity and serialization (candidate129)

`20261101094232_acquisition_review_lineage_head.sql` resolves the exact original root to its latest applicable approved chain member, checking every predecessor and complete workspace/version/kind/date-term scope. It rejects a renewal ID supplied as an original root, invalid time, withdrawn or superseded chains and future records. It does not grant authority or filter expired history away; policy/session/evidence/dependency/expiry checks remain mandatory in the future effective-authority resolver. No external grants or live call sites. Three focused cases passed21.981s.

The preceding local storage migration now takes `deal-ref` advisory lock before row locking, matching controlled writer order. The concurrent withdrawal test confirms a waiting renewal observes the newly committed withdrawal; a final six-case run adds exact-reason and saved-status assertions. Both migrations remain uncommitted until full verification. Manifest104 and full workflow integration include nine new cases; currently running rehearsal43336 covers an earlier103 snapshot and cannot prove final104 acceptance.

Candidate129 final focused evidence: six storage cases passed44.261s (23328 terminal0), including committed-withdrawal exact-reason lock-wait rejection; three identity lookup cases previously passed21.981s. Saved `evidence/2026-11-01-review-renewal-focused-result.json` with exact coverage limits and migration hashes. Earlier35909 terminal1 was solely the corrected test synchronization issue. Full43336 still running against earlier103 snapshot; final104 upgrade/API acceptance remains pending. Worktree intentionally uncommitted until final verification.

## Effective-authority integration audit (candidate130 planning, no new runtime)

The existing root-to-head helper is identity only. The next resolver must add an explicit server-derived dependency snapshot to each renewed decision before it can safely replace current-authority predicates. Resolving every original dependency to its latest head at read time alone would silently reactivate older dependent approvals.

| Current source/function | Original dependency retained | Required effective-authority behavior |
| --- | --- | --- |
| `20261101045444` / `execution_findings_match` | `execution_findings.deadline_reviews[].review_id`, date term and date-precision terms | Keep original findings unchanged; compare dates/order using the bound effective interpretation, and reject a changed effective dependency until execution is personally renewed. |
| `20261101050425` / `lock_execution_deadline_authority` | Original interpretation policy/session and minimum original expiry | Lock effective interpretation policies/memberships/sessions after resolving the complete source union; cap against effective expiry and recheck after waiting. |
| `20261101085535` / `deadline_review_current` | Original term-source verification ID plus original agreement/source journal | A refreshed scan must prove the same retained artifact/version/hash and current scanner authority; keep the original term-source reference immutable. Do not simply omit the verification check. |
| `20261101085535` / `execution_review_current` | Exact original deadline expiry and journal verification IDs | Require renewal dependency snapshot to match current effective heads; derive the source union from those exact heads, not from arbitrary latest scans. |
| `20261101085535` / `title_review_current` | Execution transition's original approval ID/expiry; retained report cutoff | Preserve transition identity, require bound effective execution identity/expiry, and retain report-freshness limits. Renewing a review cannot make an old report newer. |
| `20261101080958` / `disposition_review_current` | Latest title must equal original title ID; original execution expiry; exact latest plan | Resolve bound effective title/execution supports without changing original plan/exit/handoff references. A different proposal or exit still requires separate review. |
| `20261101085535` / `lock_disposition_handoff_authority` and transition writer | Original reviews/source unions and repeated current checks | Preserve exact receipt replay and ledger roots; current execution must use a fresh combined source/policy/dependency lock set and one post-wait evaluation. |

Required dependency snapshot: a strictly validated list of original root IDs plus the effective review IDs used by that personal decision, with kind/date-term context. Deadline reviews have no review dependencies. Execution binds each date-precision interpretation. Title binds original execution. Disposition binds original execution and title; transitive dependencies are checked recursively. Snapshot construction is server-side, under the contract serialization lock; clients cannot supply effective IDs as proof of authority. Include this snapshot in immutable audit/fingerprint/receipt discovery context, while historical receipts remain non-authorizing.

For legacy/non-renewed rows, derive their original dependency identities from existing findings/transitions; do not backfill or rewrite them. A dependency advancing to a different head makes the old dependent review require fresh personal review, even if its original expiry has not elapsed. For renewal rows, an absent/malformed/mismatched dependency snapshot fails closed. Keep current legacy predicates in place until root-aware checks, source refresh, lock helpers, writer, choices and read projections are integrated and tested together.

Acceptance additions: renew a deadline while execution remains unexpired and verify execution/title/disposition stay held; renew execution and verify title/disposition remain held; renew title and verify disposition remains held; renew each in dependency order and verify only explicitly re-reviewed chains become current. Reject changed dependency heads during source/policy lock waits and preserve all original handoff receipts. These are pending implementation, not passed tests.

## Server-derived dependency bindings (candidate131)

After a fresh disposable104 catalog inventory (`evidence/2026-11-01-review-dependencies-local-catalog.json`,5.688s), CLI-created migration20261101095023 adds nullable `renewal_dependencies` to the existing immutable review ledger. Historical rows remain null. A new BEFORE INSERT trigger, ordered after lineage validation/deal serialization, rejects supplied snapshots and derives the exact supporting root/head IDs from original findings and transitions. New deadline renewals record an empty list; execution records date interpretations; title records execution; disposition records title and execution. Withdrawn/superseded/missing supporting chains reject the insert.

Private `acquisition_review_dependencies_match` compares the stored direct bindings against current chain heads. Legacy rows require original heads, so dependency renewal cannot silently refresh them. This check intentionally does not assert transitive current authority, expiry, policy or evidence validity. Existing current predicates are unchanged; the forthcoming effective-authority resolver must recursively require each supporting review's full current checks as well as direct identity matching.

Initial two focused cases passed15.058s. Expanded withdrawn-support/scope assertions and all eleven renewal cases are running together as49999 in `/tmp/review-dependencies-eleven.log`. Manifest105 and full-catalog runner include both new dependency cases. Earlier104 full rehearsal27184 remains live and cannot prove105 acceptance; preserve it until terminal. No renewal writer/API or production activation exists.

Candidate131 verification update: eleven combined105 focused cases passed81.984s (49999 terminal0). Full104 completed0 with26 access/325 workflows/164 actual API checks, saved `evidence/2026-11-01-review-renewal-104-result.json`; it excludes105. Final105 full rehearsal49344 is live in `/tmp/review-renewal-105-upgrade-final.log`; final acceptance pending.

## Effective deadline support (candidate132)

Private migration20261101095505 resolves an original deadline to its effective review and validates the full existing current-policy/session/evidence/retention chain plus immutable source-byte identity. Same-byte fresh verification is allowed only for a renewal; historical term-source verification remains unchanged. Four local tests passed24.457s (51300). Legacy public/current functions remain untouched until the complete recursive resolver and writer are integrated. Full105 is still running; final106 verification is pending. Freeze further migration additions until this batch is verified and published.

Publication verification: full105 passed26 access/327 workflows/164 actual API checks (49344 terminal0), saved `evidence/2026-11-01-review-renewal-105-result.json`. Frozen final106 rehearsal81318 is live in `/tmp/review-renewal-106-upgrade-final.log`. Finish this run and publish before adding features; no106 acceptance claim yet.

Final batch verification:106 migrations,26 access checks,331 application workflows and164 actual API checks passed (81318 terminal0). Saved `evidence/2026-11-01-review-renewal-106-result.json`. Lineage/direct-binding/private deadline foundations are verified; recursive downstream authority, source-refresh admission, human writer, public API/UI and full renewal acceptance remain incomplete. No live activation.
