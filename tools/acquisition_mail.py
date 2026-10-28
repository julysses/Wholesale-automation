"""Pure direct-mail proposal builder. No I/O, reservations, approval or fulfillment.

Input must be a trusted repository snapshot, not user assertions of permissions.
Execution must re-evaluate eligibility and atomically reserve budget/cadence in SQL.
"""
from datetime import timedelta
import hashlib
import json
from uuid import uuid5

from schemas.acquisition_mail import MailBatchInput

VERSION = 'acquisition-mail-proposal-v1'
ACTIVE = {'approved', 'submitting', 'submitted', 'unknown'}


def prepare_mail_batch(batch: MailBatchInput) -> dict:
    if any(row.workspace_id != batch.workspace_id for row in (*batch.candidates, *batch.history)):
        raise ValueError('mail snapshot workspace mismatch')
    if len({row.job_id for row in batch.history}) != len(batch.history):
        raise ValueError('duplicate mail history job')
    if any(row.effective_at > batch.now for row in batch.history):
        raise ValueError('future mail history')
    if batch.history_as_of > batch.now:
        raise ValueError('future mail snapshot')
    # Even a complete older snapshot must be refreshed before preparation. This
    # permits bounded transport latency, not authority to execute for five minutes.
    snapshot_fresh = batch.now - batch.history_as_of <= timedelta(minutes=5)
    released = lambda row: row.status in {'failed', 'cancelled'} and row.release_evidence_ref is not None
    charged = [row for row in batch.history if row.status != 'proposed' and not released(row)]
    committed = sum(row.cost_cents for row in charged if row.campaign_id == batch.campaign_id)
    remaining = max(0, batch.budget_cents - committed)
    global_reasons = []
    if not batch.history_complete or not snapshot_fresh:
        global_reasons.append('HISTORY_INCOMPLETE_OR_STALE')
    if batch.quote_expires_at <= batch.now:
        global_reasons.append('QUOTE_EXPIRED')
    if committed > batch.budget_cents:
        global_reasons.append('BUDGET_ALREADY_EXCEEDED')
    cutoff = batch.now - timedelta(days=batch.frequency_days)
    # Unknown/submitted/in-flight reservations block indefinitely until reconciled.
    # Failed/cancelled outcomes without release evidence retain this same hold.
    cadence = [row for row in charged if row.effective_at > cutoff
               or row.status in ACTIVE or row.status in {'failed', 'cancelled'}]
    held_properties = {row.property_id for row in cadence}
    held_addresses = {row.recipient_address_key for row in cadence}
    seen_properties, seen_addresses = set(), set()
    selected, held = [], []
    # Reject conflicting duplicate canonical property snapshots rather than choose
    # an arbitrary recipient/owner. Identical copies collapse deterministically.
    candidates = {}
    for row in batch.candidates:
        previous = candidates.get(row.property_id)
        if previous is not None and previous != row:
            raise ValueError('conflicting property candidates')
        candidates[row.property_id] = row
    ordered = sorted(candidates.values(), key=lambda row: (-(row.score if row.score is not None else -1), str(row.property_id)))
    for row in ordered:
        reasons = list(global_reasons)
        if row.state != 'TX' or row.county not in {'Dallas', 'Collin'}:
            reasons.append('OUTSIDE_INITIAL_TERRITORY')
        if row.score is None or row.score < batch.minimum_score:
            reasons.append('SCORE_MISSING_OR_BELOW_MINIMUM')
        if (row.address_status != 'verified' or not row.recipient_address_key
                or row.address_evidence_ref is None or row.address_expires_at is None
                or row.address_expires_at <= batch.now):
            reasons.append('ADDRESS_NOT_VERIFIED')
        if row.owner_status != 'living':
            reasons.append('OWNER_REVIEW_REQUIRED')
        if row.preference != 'clear':
            reasons.append('CONTACT_PREFERENCE_HOLD')
        if (row.eligibility != 'ALLOW' or row.eligibility_expires_at is None
                or row.eligibility_expires_at <= batch.now):
            reasons.append('ELIGIBILITY_NOT_ALLOWED')
        if row.property_id in held_properties or row.recipient_address_key in held_addresses:
            reasons.append('FREQUENCY_OR_PENDING_JOB_HOLD')
        if row.property_id in seen_properties or row.recipient_address_key in seen_addresses:
            reasons.append('DUPLICATE_RECIPIENT')
        if len(selected) >= batch.maximum_pieces:
            reasons.append('BATCH_LIMIT')
        if remaining < batch.unit_cost_cents:
            reasons.append('BUDGET_LIMIT')
        if reasons:
            held.append({'property_id': str(row.property_id), 'reason_codes': reasons})
            continue
        seen_properties.add(row.property_id)
        seen_addresses.add(row.recipient_address_key)
        selected.append({'property_id': str(row.property_id), 'lead_id': str(row.lead_id),
                         'owner_id': str(row.owner_id), 'score': row.score,
                         'tracking_id': str(uuid5(batch.batch_id, str(row.property_id))),
                         'cost_cents': batch.unit_cost_cents,
                         'address_evidence_ref': str(row.address_evidence_ref),
                         'eligibility_decision_id': str(row.eligibility_decision_id)})
        remaining -= batch.unit_cost_cents
    snapshot = batch.model_dump(mode='json')
    snapshot['candidates'] = [row.model_dump(mode='json') for row in ordered]
    snapshot['history'].sort(key=lambda row: row['job_id'])
    snapshot_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return {'snapshot_sha256': snapshot_hash, 'version': VERSION, 'status': 'proposed', 'execution_authorized': False,
            'workspace_id': str(batch.workspace_id), 'campaign_id': str(batch.campaign_id),
            'batch_id': str(batch.batch_id), 'template_id': str(batch.template_id),
            'template_version': batch.template_version, 'format': batch.format,
            'tracking_destination_ref': str(batch.tracking_destination_ref),
            'vendor_id': batch.vendor_id, 'quote_ref': str(batch.quote_ref), 'currency': batch.currency,
            'prepared_at': batch.now.isoformat(), 'selected': selected, 'held': held,
            'committed_cents': committed if batch.history_complete and snapshot_fresh else None,
            'proposed_cents': len(selected) * batch.unit_cost_cents,
            'remaining_cents': remaining if batch.history_complete and snapshot_fresh else None,
            'reason_codes': global_reasons}
