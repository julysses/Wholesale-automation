"""Reviewed written buyer consent. This never enables a campaign or sends SMS."""
from datetime import datetime, timezone
from uuid import UUID
from urllib.parse import urlsplit
import re

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator


class ConsentReview(BaseModel):
    request_id: UUID
    phone: str
    source_type: str
    source_url: str = Field(max_length=2000)
    sha256: str
    consented_at: datetime
    disclosure: str = Field(min_length=40, max_length=4000)
    affirmative_action: str = Field(min_length=3, max_length=2000)
    reviewed_written_evidence: bool
    accepted: bool

    @field_validator('source_type')
    @classmethod
    def source(cls, value):
        if value not in {'signed_document','written_web_form'}:raise ValueError('Use retained written evidence')
        return value

    @field_validator('source_url')
    @classmethod
    def url(cls, value):
        parsed=urlsplit(value)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or re.search(r'\s',value):
            raise ValueError('Use an HTTPS evidence reference without embedded credentials')
        return value

    @field_validator('sha256')
    @classmethod
    def digest(cls, value):
        if not re.fullmatch('[0-9a-f]{64}',value):raise ValueError('Use the SHA-256 of the retained evidence')
        return value

    @field_validator('consented_at')
    @classmethod
    def date(cls, value):
        if value.tzinfo is None:raise ValueError('Include the consent time zone')
        if value>datetime.now(timezone.utc):raise ValueError('Consent cannot be in the future')
        return value


def status(db,buyer,operator):
    try:
        result=db.rpc('buyer_sms_consent_status',{'p_buyer':str(buyer),'p_operator':operator}).execute().data
        if (not isinstance(result,dict) or result.get('buyer_id')!=str(buyer)
            or any(type(result.get(k)) is not bool for k in ['can_review','consent_ready','suppressed','sending_available'])):
            raise ValueError('Unconfirmed consent status')
        return result
    except Exception as exc:
        if (getattr(exc,'pgcode',None) or getattr(exc,'code',None))=='P0002':raise HTTPException(404,'Buyer not found') from None
        raise HTTPException(503,'Buyer SMS consent could not be confirmed') from None


def review(db,buyer,operator,req):
    if req.reviewed_written_evidence is not True:
        raise HTTPException(422,'Review the retained written evidence before saving')
    evidence=req.model_dump(mode='json',exclude={'request_id','phone','accepted'})
    try:
        result=db.rpc('review_buyer_sms_consent',{'p_id':str(req.request_id),'p_buyer':str(buyer),
            'p_operator':operator,'p_phone':req.phone,'p_evidence':evidence,'p_accepted':req.accepted}).execute().data
        if (not isinstance(result,dict) or result.get('id')!=str(req.request_id)
            or result.get('buyer_id')!=str(buyer) or result.get('saved') is not True
            or result.get('accepted') is not req.accepted):raise ValueError('Unconfirmed consent receipt')
        return result
    except Exception as exc:
        code=getattr(exc,'pgcode',None) or getattr(exc,'code',None)
        if code=='42501':raise HTTPException(403,'An approved administrator must review buyer SMS consent') from None
        if code=='P0002':raise HTTPException(404,'Buyer not found') from None
        if code in {'22023','22007','22008'}:raise HTTPException(409,'Evidence, reference, buyer phone or suppression changed. Review before saving.') from None
        raise HTTPException(503,'Consent receipt is unconfirmed. Keep the same reference when retrying.') from None
