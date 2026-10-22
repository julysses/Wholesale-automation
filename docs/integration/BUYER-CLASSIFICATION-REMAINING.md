# Historical investigation — superseded by candidate implementation

See [BUYER-ANALYSIS-RECOVERY.md](BUYER-ANALYSIS-RECOVERY.md) for the new retained protocol and its verification limits. The following describes the pre-repair investigation, not current candidate behavior. Live acceptance is still open.

# Remaining explicit buyer analysis — October 22 investigation

Manual buyer creation is covered separately; this gate is still open.
Current POST /api/buyers/{id}/classify and /api/buyers/score return queued status
and use in-process BackgroundTasks. Failures are logged rather than durably
returned to the operator; the UI asks for a later refresh. Writes are separate
per buyer and can use stale profile/history inputs. There is no stable request
receipt or one-way paid classification authorization.

A configuration failure was reproduced offline before SDK construction:
BuyerIntelligenceAgent._call_claude references self.settings.anthropic_api_key,
but BaseAgent initializes _client/_model and has no settings attribute. The
result is AttributeError. The helper also creates a default-retrying SDK client,
and malformed classification output falls back to landlord. Do not merely enable
that paid path while leaving unknown outcomes, invalid output or lost saves unsafe.
No actual provider request was made in this investigation.

Next implementation: immutable per-operator requests and frozen complete inputs;
atomic free-score commit with current-input/version checks; single-buyer bounded
classification claim before a non-retrying timed SDK call; retained result and
unknown/stale/error states; read-only recovery without another charge. Persist
validated model output only, leaving existing classification unchanged on invalid
output. Preserve consent/DNC/availability/manual tags and current profile edits.
The operator UI must show confirmed outcomes and explicit bounded continuation,
not queued success. No automatic background scoring/classification on CSV/manual
creation, broad scheduler enablement, consent inference or provider sending.

Required proof: independent SQL sessions/one paid stub, lost claim/result/commit
responses, changed buyer/history and deletion, invalid model output, role boundaries,
score-version stability, complete multi-page history, modal recovery and actual
provider/availability acceptance under separately authorized scope. Current tests
for import/scoring are not evidence that this explicit-analysis gate is complete.
