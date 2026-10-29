"""Create a non-executing preview from a validated, current server projection.

No caller snapshots are accepted by the HTTP endpoint. This loader does not resolve
review evidence files, verify postal deliverability, select recipients or send mail.
"""
from datetime import datetime, timedelta
from uuid import UUID, NAMESPACE_URL, uuid5

from schemas.acquisition_mail_preparation import from_epoch
from schemas.acquisition_mail_proof import MailProofContext
from schemas.acquisition_mail_render import MailTemplateSnapshot, MailDestinationSnapshot, MailContentReview, MailRenderInput
from tools.acquisition_mail_render import content_binding, digest, render_mail_proof, safe_text

VERSION = 'acquisition-mail-proof-loader-v1'


class ProofUnavailable(ValueError):
    """The records are readable, but a fresh review is needed before previewing."""


def build_reviewed_mail_proof(raw: dict, *, workspace_id: UUID, campaign_id: UUID, content_id: UUID,
                             lead_id: UUID, now: datetime) -> dict:
    context = MailProofContext.model_validate(raw)
    if (context.workspace_id, context.campaign_id, context.content_id, context.lead_id) != (workspace_id, campaign_id, content_id, lead_id):
        raise ValueError('Proof scope does not match the request')
    if now.utcoffset() is None:
        raise ValueError('Proof clock requires a time zone')
    # Bound read/transport latency only; no cached preparation is execution authority.
    if not -timedelta(seconds=5) <= now - context.checked_at <= timedelta(seconds=30):
        raise ProofUnavailable('Refresh the content and property records before previewing')
    state = context.review_state
    if not state.review_current or state.latest_review is None or state.preparation is None:
        raise ProofUnavailable('Current content approval is required')
    review = state.latest_review
    snapshot = state.preparation.snapshot
    destination = snapshot.destination
    if now >= min(review.expires_at, from_epoch(destination.expires_epoch)):
        raise ProofUnavailable('Content or destination evidence expired before rendering')
    scope = dict(workspace_id=workspace_id, campaign_id=campaign_id)
    template = MailTemplateSnapshot(**scope, **snapshot.template.model_dump(exclude={'creative_id'}))
    route = MailDestinationSnapshot(**scope, id=destination.destination_id, version=destination.version,
        mode=destination.mode, value=destination.value, verification_ref=destination.verification_ref,
        verified_at=from_epoch(destination.verified_epoch), expires_at=from_epoch(destination.expires_epoch), revoked=False)
    # Reconstruct the renderer binding from validated server-owned records only.
    # The SQL preparation hash has already been validated against the persisted approval.
    decision = MailContentReview(**scope, id=review.id, approver_id=review.actor_id, evidence_ref=review.evidence_ref,
        binding_digest=content_binding(template, route, snapshot.company_name), status='approved',
        reviewed_at=review.created_at, expires_at=review.expires_at)
    property_row = context.property
    for value in (property_row.address_std, property_row.unit, property_row.city, property_row.state, property_row.zip):
        if value is not None:
            safe_text(value)
            if any(c in value for c in '{}'):
                raise ValueError('Canonical address cannot contain substitution tokens')
    # Preserve units and canonical text. This is the subject property, not a verified mailing address.
    street = property_row.address_std + (f'\nUnit {property_row.unit}' if property_row.unit is not None else '')
    address = street + f'\n{property_row.city}, {property_row.state}' + (f' {property_row.zip}' if property_row.zip is not None else '')
    preview_id = uuid5(NAMESPACE_URL, f'wholesaleos:mail-preview:{workspace_id}:{campaign_id}:{content_id}:{review.id}:{property_row.property_id}')
    proof = render_mail_proof(MailRenderInput(**scope, property_id=property_row.property_id, tracking_id=preview_id,
        company_name=snapshot.company_name, property_address=address, now=now, template=template, destination=route, review=decision))
    source_digest = digest({'loader_version': VERSION, 'preparation_hash': review.preparation_hash,
        'content_id': str(content_id), 'content_review_id': str(review.id), 'content_review_version': review.version,
        'content_evidence_hash': review.evidence_hash, 'property': property_row.model_dump(mode='json')})
    render_digest = proof.pop('proof_digest')
    return {**proof, 'proof_loader_version': VERSION, 'proof_kind': 'internal_content_preview',
        'content_id': str(content_id), 'content_version': review.version, 'lead_id': str(lead_id),
        'tracking_id_kind': 'preview_only', 'source_checked_at': context.checked_at.isoformat(),
        'preparation_hash': review.preparation_hash, 'source_digest': source_digest, 'render_digest': render_digest,
        'proof_digest': digest({'loader_version': VERSION, 'render_digest': render_digest, 'source_digest': source_digest}),
        'postal_verified': False, 'recipient_authorized': False, 'vendor_proof': False}
