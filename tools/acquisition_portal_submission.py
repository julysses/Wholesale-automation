"""Server orchestration for an exact inquiry; no public endpoint or activation.

The eventual receiver supplies a bounded, validated OnlineOfferRequest and a
trusted HMAC network identity. Form wording comes only from the database.
"""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool

from schemas.acquisition_online_offer import OnlineOfferRequest, OfferFormDefinition
from tools.acquisition_online_offer import prepare_online_offer
from tools.acquisition_portal_admission import admit_portal_request
from tools.acquisition_portal_bot import BotConfig, BotRejected, BotUnavailable, verify_portal_bot


class PortalReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    submission_id: UUID
    status: Literal['received']
    duplicate: StrictBool


class PortalSubmissionUnconfirmed(HTTPException):
    def __init__(self):
        super().__init__(503, 'Submission was not confirmed; preserve the same inquiry for retry',
                         headers={'Cache-Control': 'no-store'})


async def submit_portal_inquiry(store, config: BotConfig, *, form_key: str, inquiry: OnlineOfferRequest,
                                network_hash: str, bot_token: str, bot_transport=None) -> PortalReceipt:
    if not isinstance(inquiry, OnlineOfferRequest):
        raise HTTPException(422, 'Validated inquiry required', headers={'Cache-Control': 'no-store'})
    try:
        raw = await store.request('POST', 'rpc/read_acquisition_public_form', body={'p_form_key': form_key})
        try:
            definition = OfferFormDefinition.model_validate(raw)
            if definition.form_key != form_key:
                raise ValueError('Form identity mismatch')
        except (ValueError, TypeError):
            raise HTTPException(503, 'Offer request form is unavailable') from None
        try:
            prepared = prepare_online_offer(inquiry, definition)
        except ValueError:
            raise HTTPException(409, 'Form changed; review current wording before submitting') from None
        admission = await admit_portal_request(store, form_key=form_key, network_hash=network_hash, purpose='submit',
                                               submission_id=inquiry.submission_id, request_hash=prepared['request_hash'])
        try:
            verification = await verify_portal_bot(config, token=bot_token, submission_id=inquiry.submission_id,
                                                   request_hash=prepared['request_hash'], transport=bot_transport)
        except BotRejected:
            raise HTTPException(400, 'Complete a new verification challenge') from None
        except BotUnavailable:
            raise HTTPException(503, 'Verification is temporarily unavailable') from None
        if admission.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(409, 'Request capacity expired; retry the same inquiry')
        proof = {'provider': verification.provider, 'submission_id': str(verification.submission_id),
                 'request_hash': verification.request_hash, 'token_hash': verification.token_hash,
                 'verification_id': str(verification.verification_id), 'hostname': verification.hostname,
                 'action': verification.action, 'challenged_at': verification.challenged_at.isoformat(),
                 'verified_at': verification.verified_at.isoformat(), 'expires_at': verification.expires_at.isoformat()}
        try:
            raw = await store.request('POST', 'rpc/complete_acquisition_portal_request', body={
                'p_attempt': str(admission.attempt_id), 'p_prepared': prepared, 'p_bot': proof})
        except HTTPException as error:
            if error.status_code >= 500:
                raise PortalSubmissionUnconfirmed() from None
            raise
        try:
            receipt = PortalReceipt.model_validate(raw)
            if receipt.submission_id != inquiry.submission_id:
                raise ValueError('Receipt identity changed')
        except (ValueError, TypeError):
            raise PortalSubmissionUnconfirmed() from None
        return receipt
    except HTTPException as error:
        error.headers = {**(error.headers or {}), 'Cache-Control': 'no-store'}
        raise
