# Review renewal implementation contract

Status: design and request/receipt validation only. No renewal endpoint, database writer, policy or activation exists yet. This document keeps the full lifecycle objective open and replaces the unsafe shortcut of extending an old approval's expiry.

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
