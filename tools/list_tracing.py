"""Receipt-driven tracing workflow. No configured production provider or implicit send."""
import re
from typing import Literal, Protocol
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from tools.operational_alerts import record_provider_alert

class Contact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    phone: str | None = Field(default=None, pattern=r'^\+1[2-9][0-9]{9}$')
    email: str | None = Field(default=None, max_length=320, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    phone_type: Literal['mobile','landline','voip','unknown'] = 'unknown'
    name: str | None = Field(default=None, max_length=200)

    @model_validator(mode='after')
    def destination(self):
        if not self.phone and not self.email:
            raise ValueError('A trace contact requires a phone or email')
        return self

class TraceReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    request_id: str
    lead_id: str
    provider: str
    input_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    provider_receipt: str = Field(min_length=1, max_length=255)
    actual_cents: int = Field(ge=0)
    contacts: list[Contact] = Field(max_length=20)

class TraceProvider(Protocol):
    name: str
    def trace(self, *, request_id: str, lead_id: str, input_hash: str, payload: dict) -> TraceReceipt: ...

class TraceUnconfirmed(RuntimeError):
    pass


def _rpc(db, name, params):
    value = db.rpc(name, params).execute().data
    if not isinstance(value, dict):
        raise TraceUnconfirmed('Trace database receipt is unconfirmed')
    return value


def _request(value, reference, lead, provider, maximum):
    row = value.get('request')
    if (not isinstance(row, dict) or row.get('id') != reference or row.get('lead_id') != lead
        or row.get('provider') != provider or type(row.get('reserved_cents')) is not int
        or row['reserved_cents'] != maximum or not isinstance(row.get('input_hash'), str)
        or not re.fullmatch(r'[a-f0-9]{64}',row['input_hash'])):
        raise TraceUnconfirmed('Trace request identity is unconfirmed')
    return row


def _unknown(db, reference, lead):
    try:
        _rpc(db,'settle_list_trace',{'p_id':reference,'p_state':'unknown','p_actual_cents':None,'p_provider_receipt':None,'p_result_hash':None})
    except Exception:
        pass  # Submitted state still blocks a retry if the uncertainty write fails.
    try:
        record_provider_alert(db,'skip_trace',reference,'unknown',lead)
    except Exception:
        pass  # Caller receives an explicit error even if the operator alert is unavailable.


def trace_lead(db, provider: TraceProvider, request_id: UUID, lead_id: UUID, maximum_cents: int, *, enabled: bool = False):
    """Caller must persist request_id and enable only after provider/budget acceptance.

    A lost claim acknowledgement is never authorization to call. Provider adapters
    must submit once and return correlated billing/contact evidence, never guesses.
    """
    if enabled is not True:
        return {'blocked':'tracing_disabled'}
    if type(maximum_cents) is not int or maximum_cents <= 0:
        raise ValueError('Verified maximum cost is required')
    reference,lead=str(request_id),str(lead_id)
    reserved=_rpc(db,'prepare_list_trace',{'p_id':reference,'p_lead':lead,'p_provider':provider.name,'p_max_cents':maximum_cents})
    if reserved.get('blocked'):
        return reserved
    row=_request(reserved,reference,lead,provider.name,maximum_cents)
    if row.get('state') != 'reserved':
        return {'request':row,'dispatch':False,'contacts_saved':reserved.get('contacts_saved',0)}
    try:
        claimed=_rpc(db,'claim_list_trace',{'p_id':reference,'p_input_hash':row['input_hash']})
        if claimed.get('blocked'):
            return claimed
        active=_request(claimed,reference,lead,provider.name,maximum_cents)
        if claimed.get('dispatch') is not True:
            return claimed
        if active.get('state')!='submitted' or active.get('input_hash')!=row['input_hash'] or claimed.get('input')!=row.get('input_snapshot'):
            raise TraceUnconfirmed('Claim does not match reserved input')
        receipt=TraceReceipt.model_validate(provider.trace(request_id=reference,lead_id=lead,input_hash=row['input_hash'],payload=claimed['input']))
        if (receipt.request_id!=reference or receipt.lead_id!=lead or receipt.provider!=provider.name
            or receipt.input_hash!=row['input_hash'] or receipt.actual_cents>maximum_cents):
            raise TraceUnconfirmed('Provider receipt does not match trace request')
        completed=_rpc(db,'complete_list_trace',{'p_id':reference,'p_provider':provider.name,'p_input_hash':row['input_hash'],
            'p_actual_cents':receipt.actual_cents,'p_provider_receipt':receipt.provider_receipt,
            'p_contacts':[c.model_dump() for c in receipt.contacts]})
        saved=_request(completed,reference,lead,provider.name,maximum_cents)
        if (saved.get('state')!='completed' or saved.get('actual_cents')!=receipt.actual_cents
            or saved.get('provider_job_id')!=receipt.provider_receipt or saved.get('input_hash')!=receipt.input_hash
            or completed.get('contacts_saved')!=len(receipt.contacts)):
            raise TraceUnconfirmed('Trace contacts or billing persistence is unconfirmed')
        return completed
    except Exception as exc:
        _unknown(db,reference,lead)
        raise TraceUnconfirmed('Trace outcome requires reconciliation; do not resubmit') from exc
