"""Immutable form registry through actual local PostgREST; synthetic drafts only."""
from uuid import UUID
from urllib.parse import urlencode

from web.api.acquisition_offer_forms_api import OfferFormReceipt, OfferFormVersion


def verify_offer_forms_http(db, request, token, other, workspace):
    campaign='99500000-0000-4000-8000-000000000001'
    identity='99500000-0000-4000-8000-000000000002'
    newer='99500000-0000-4000-8000-000000000003'
    status,_=request('/rpc/create_acquisition_campaign',token(),{
        'p_id':campaign,'p_workspace':workspace,'p_name':'Synthetic form HTTP',
        'p_channel':'online_offer','p_budget_cents':0,'p_currency':'USD'})
    if status!=200:raise AssertionError('Offer form HTTP campaign setup failed')
    definition={'form_key':'synthetic-http-form','version':'v1','privacy_acknowledged':'Synthetic privacy wording',
                'human_callback_requested':'Synthetic optional human callback','email_reply_requested':'Synthetic optional email reply'}
    body={'p_id':identity,'p_workspace':workspace,'p_campaign':campaign,'p_expected_revision':0,'p_definition':definition}
    path='/rpc/save_acquisition_offer_form'
    for caller in (token(other),None):
        if request(path,caller,body)[0] not in (401,403):raise AssertionError('Unauthorized form save accepted')
    for duplicate in (False,True):
        status,result=request(path,token(),body)
        if status!=200:raise AssertionError('Offer form HTTP save failed')
        receipt=OfferFormReceipt.model_validate(result)
        if (receipt.id,receipt.workspace_id,receipt.campaign_id)!=(UUID(identity),UUID(workspace),UUID(campaign)) or receipt.duplicate is not duplicate:
            raise AssertionError('Offer form HTTP identity or retry changed')
    for invalid in (body|{'p_definition':definition|{'privacy_acknowledged':'Changed'}},
                    body|{'p_id':newer,'p_definition':definition|{'version':'v2'}}):
        status,error=request(path,token(),invalid)
        if status==200 or error.get('code') not in ('23505','40001'):
            raise AssertionError('Conflicting form HTTP save accepted')
    second=body|{'p_id':newer,'p_expected_revision':1,'p_definition':definition|{'version':'v2'}}
    status,result=request(path,token(),second)
    if status!=200 or OfferFormReceipt.model_validate(result).revision!=2:
        raise AssertionError('Form HTTP next version failed')
    params={'select':','.join(OfferFormVersion.model_fields),'workspace_id':'eq.'+workspace,
            'campaign_id':'eq.'+campaign,'acquisition_form_key':'eq.synthetic-http-form','order':'id','limit':'1'}
    listing='/lead_form_configs?'+urlencode(params)
    status,rows=request(listing,token())
    if status!=200 or len(rows)!=1:raise AssertionError('Form HTTP listing failed')
    first=OfferFormVersion.model_validate(rows[0])
    if first.id!=UUID(identity) or first.acquisition_form_definition.model_dump()!=definition:
        raise AssertionError('Form HTTP original definition changed')
    status,rows=request('/lead_form_configs?'+urlencode(params|{'id':'gt.'+identity}),token())
    if status!=200 or len(rows)!=1 or OfferFormVersion.model_validate(rows[0]).id!=UUID(newer):
        raise AssertionError('Form HTTP cursor failed')
    if request(listing,token(other))!=(200,[]) or request(listing,None)!=(200,[]):
        raise AssertionError('Form HTTP history scope leaked')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_offer_form'")[0]['n']!=2:
        raise AssertionError('Form HTTP retries duplicated audit')

    def after_session_revocation():
        if request(path,token(),second)[0]!=403 or request(listing,token())!=(200,[]):
            raise AssertionError('Revoked session retains form access')
    return ['form HTTP exact retry and immutable version history','form HTTP conflicting request and stale revision rejected',
            'form HTTP tenant and anonymous isolation','form HTTP typed paginated history','form HTTP revoked session denied'],after_session_revocation
