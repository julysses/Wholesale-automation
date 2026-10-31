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

    publication_checks=verify_public_display_http(db,request,token,other,workspace,campaign,identity,definition)
    portal_checks=verify_portal_receipt_http(db,request,token,other,workspace,definition)
    legacy_checks=verify_legacy_receipt_http(db,request,token,workspace,identity)

    def after_session_revocation():
        if request(path,token(),second)[0]!=403 or request(listing,token())!=(200,[]):
            raise AssertionError('Revoked session retains form access')
    return ['form HTTP exact retry and immutable version history','form HTTP conflicting request and stale revision rejected',
            'form HTTP tenant and anonymous isolation','form HTTP typed paginated history','form HTTP revoked session denied']+publication_checks+legacy_checks+portal_checks,after_session_revocation


def verify_legacy_receipt_http(db,request,token,workspace,scoped_form):
    service=token(role='service_role')
    form='99600000-0000-4000-8000-000000000001';receipt='99600000-0000-4000-8000-000000000002'
    db.query("INSERT INTO public.lead_form_configs(id,name,slug,active) VALUES(%s,'Synthetic legacy','synthetic-legacy-http',false)",[form])
    reserve={'p_request_id':receipt,'p_submission':{'form_id':form,'raw_answers':{}},'p_manifest':{'synthetic':True}}
    status,error=request('/rpc/reserve_form_submission',service,reserve|{'p_submission':{'form_id':scoped_form,'raw_answers':{}}})
    if status!=403 or error.get('message')!='Use acquisition submission workflow':
        raise AssertionError('Legacy reservation accepted scoped form')
    for expected in ('created','replayed'):
        status,result=request('/rpc/reserve_form_submission',service,reserve)
        if status!=200 or result.get('status')!=expected or result.get('submission_id')!=receipt:
            raise AssertionError('Legacy reservation behavior changed')
    body={'p_submission_id':receipt,'p_lead':{'property_address':'Synthetic legacy gateway address','city':'Dallas',
        'state':'TX','zip_code':'75201','source':'web_form','inbound_channel':'web_form','status':'qualified_cold',
        'precision_tier':3,'priority_tier':'C','ai_calling_paused':True,'_intake_recovery_only':True}}
    lead=None
    for created in (True,False):
        status,result=request('/rpc/finalize_form_submission',service,body)
        if status!=200 or result.get('created') is not created or not result.get('lead_id'):
            raise AssertionError('Legacy finalization/recovery behavior changed')
        if lead is not None and result['lead_id']!=lead:raise AssertionError('Legacy recovery duplicated lead')
        lead=result['lead_id']
    if db.query('SELECT count(*) AS n FROM public.tasks WHERE id=%s AND lead_id=%s',[receipt,lead])[0]['n']!=1:
        raise AssertionError('Legacy recovery task was duplicated')
    if db.query('SELECT count(*) AS n FROM public.app_notifications WHERE lead_id=%s',[lead])[0]['n']!=1:
        raise AssertionError('Legacy recovery alert was duplicated')
    status,_=request('/rpc/bind_acquisition_lead',token(),{'p_workspace':workspace,'p_lead':lead,'p_property':None})
    if status!=200:raise AssertionError('Synthetic legacy lead enrollment failed')
    for path,payload in (('/rpc/reserve_form_submission',reserve),('/rpc/finalize_form_submission',body)):
        status,error=request(path,service,payload)
        if status!=403 or error.get('message')!='Use acquisition submission workflow':
            raise AssertionError('Legacy retry bypassed enrolled lead scope')
    return ['legacy receipt HTTP scoped form denied','legacy receipt HTTP reservation and finalization retry preserve one lead task alert',
            'legacy receipt HTTP enrolled lead recovery denied']


def verify_public_display_http(db,request,token,other,workspace,campaign,identity,definition):
    """Privileged synthetic configuration, then real signed service RPC calls."""
    path='/rpc/read_acquisition_public_form'
    body={'p_form_key':definition['form_key']}
    service=token(role='service_role')
    db.query('INSERT INTO private.acquisition_form_publications(form_key,workspace_id,campaign_id,form_id) VALUES(%s,%s,%s,%s)',
             [definition['form_key'],workspace,campaign,identity])

    def unavailable(payload=body):
        status,result=request(path,service,payload)
        if status!=403 or result.get('code')!='42501' or result.get('message')!='Form unavailable':
            raise AssertionError('Unavailable form did not fail closed without routing details')
    unavailable();unavailable({'p_form_key':'missing-form'})
    for jwt in (None,token(),token(other)):
        if request(path,jwt,body)[0] not in (401,403):
            raise AssertionError('Browser JWT can call service-only display RPC')
    for jwt in (token(role='service_role',key='wrong-synthetic-signing-key-of-sufficient-length'),
                token(role='service_role',expiry=1)):
        if request(path,jwt,body)[0]!=401:raise AssertionError('Invalid service JWT accepted')
    db.query("UPDATE private.acquisition_form_publications SET enabled=true,phase_one_approval_ref='synthetic-phase-1',phase_two_approval_ref='synthetic-phase-2',wording_approval_ref='synthetic-wording',publication_approval_ref='synthetic-display',valid_from=clock_timestamp()-interval '1 minute',expires_at=clock_timestamp()+interval '1 hour'")
    if request(path,service,body)!=(200,definition):
        raise AssertionError('Service display RPC changed exact wording or exposed extra fields')
    status,error=request('/lead_form_submissions',service,{'id':'99500000-0000-4000-8000-000000000004',
        'form_id':identity,'raw_answers':{'synthetic':'test'}})
    if status!=403 or error.get('code')!='42501' or error.get('message')!='Use acquisition submission workflow':
        raise AssertionError('Legacy submission did not reach the acquisition guard')
    # A second saved version already exists. Publication must still select v1.
    for injection in ({'p_workspace':workspace},{'p_version':'v2'},{'p_definition':definition}):
        if request(path,service,body|injection)[0]==200:
            raise AssertionError('Public lookup accepted caller-controlled routing or wording')
    db.query("UPDATE public.workspaces SET status='suspended' WHERE id=%s",[workspace])
    unavailable()
    db.query("UPDATE public.workspaces SET status='active' WHERE id=%s",[workspace])
    db.query('UPDATE private.acquisition_activation SET enabled=false')
    unavailable()
    db.query('UPDATE private.acquisition_activation SET enabled=true')
    db.query("UPDATE private.acquisition_form_publications SET expires_at=clock_timestamp()+interval '50 milliseconds'")
    db.query('SELECT pg_sleep(0.06)')
    unavailable()
    db.query('UPDATE private.acquisition_form_publications SET enabled=false')
    if request('/lead_form_configs?select=id&workspace_id=eq.'+workspace,None)!=(200,[]):
        raise AssertionError('Publication exposed private form rows anonymously')
    return ['public display HTTP signed service role required','public display HTTP exact selected version and minimal projection',
            'public display HTTP legacy submission reaches and rejects at acquisition guard',
            'public display HTTP rejects routing injection','public display HTTP disabled expired suspended and activation gates']


def verify_portal_receipt_http(db,request,token,other,workspace,definition):
    from schemas.acquisition_online_offer import OnlineOfferRequest, OfferFormDefinition
    from tools.acquisition_online_offer import prepare_online_offer
    identity='99700000-0000-4000-8000-000000000001'
    prepared=prepare_online_offer(OnlineOfferRequest.model_validate({
        'submission_id':identity,'form_version':'v1','seller':{'name':'Synthetic Portal','email':'synthetic@example.test'},
        'property':{'address':'123 Synthetic Portal','city':'Dallas','state':'TX','postal_code':'75201','authority':'owner',
          'condition':'unsure','occupancy':'vacant','timeline':'flexible','motivation':'Synthetic QA','asking_price':None},
        'selections':{'privacy_acknowledged':True,'email_reply_requested':False}}),OfferFormDefinition.model_validate(definition))
    from uuid import uuid4,uuid5
    from datetime import datetime,timedelta,timezone
    service=token(role='service_role')
    legacy={'p_form_key':definition['form_key'],'p_submission':identity,'p_prepared':prepared}
    if request('/rpc/accept_acquisition_online_offer',service,legacy)[0]!=403:
        raise AssertionError('Unverified portal bypass remains callable')
    db.query("UPDATE private.acquisition_form_publications SET enabled=true,valid_from=clock_timestamp()-interval '1 minute',expires_at=clock_timestamp()+interval '1 hour'")
    db.query("UPDATE private.acquisition_portal_admission_policy SET enabled=true,bot_hostname='seller.example.test',approval_ref='synthetic-completion',valid_from=clock_timestamp()-interval '1 minute',expires_at=clock_timestamp()+interval '1 hour'")
    now=datetime.now(timezone.utc);token_hash='e'*64
    proof=dict(provider='turnstile',hostname='seller.example.test',action='acquisition_offer',submission_id=identity,
        request_hash=prepared['request_hash'],token_hash=token_hash,
        verification_id=str(uuid5(UUID('32c074f8-362c-4d9a-a84c-1851f32e67b4'),identity+':'+prepared['request_hash']+':'+token_hash)),
        challenged_at=now.isoformat(),verified_at=now.isoformat(),expires_at=(now+timedelta(seconds=300)).isoformat())
    def ticket():
        attempt=str(uuid4())
        status,row=request('/rpc/admit_acquisition_portal_request',service,{'p_attempt':attempt,'p_form_key':definition['form_key'],
            'p_network_hash':'b'*64,'p_purpose':'submit','p_submission':identity,'p_request_hash':prepared['request_hash']})
        if status!=200 or row.get('admitted') is not True:raise AssertionError('Completion admission unavailable')
        return {'p_attempt':attempt,'p_prepared':prepared,'p_bot':proof|{'verified_at':datetime.now(timezone.utc).isoformat()}}
    path='/rpc/complete_acquisition_portal_request';body=ticket()
    for actor in (None,token(),token(other)):
        if request(path,actor,body)[0] not in (401,403):raise AssertionError('Browser can complete portal persistence directly')
    for duplicate in (False,True):
        if duplicate:body=ticket()
        if request(path,service,body)!=(200,{'submission_id':identity,'status':'received','duplicate':duplicate}):
            raise AssertionError('Verified portal HTTP receipt projection or retry failed')
        if request(path,service,body)[0]!=403:raise AssertionError('Consumed admission was reused')
    if request('/rpc/accept_acquisition_online_offer',service,legacy)[0]!=403:
        raise AssertionError('Enabled policy restored legacy bypass')
    listing='/lead_form_submissions?id=eq.'+identity+'&select=id,workspace_id,raw_answers'
    status,rows=request(listing,token())
    if status!=200 or len(rows)!=1 or rows[0]['workspace_id']!=workspace or rows[0]['raw_answers']!=prepared['request_evidence']:
        raise AssertionError('Portal evidence changed or owner cannot review it')
    if request(listing,token(other))!=(200,[]):raise AssertionError('Other workspace can read portal evidence')
    for actor in (token(),token(other),service):
        status,_=request('/lead_form_submissions',actor,{'id':'99700000-0000-4000-8000-000000000002','raw_answers':{},'workspace_id':workspace})
        if status not in (401,403):raise AssertionError('Raw portal receipt insertion accepted')
    for table in ('seller_intakes','acquisition_lead_sources'):
        status,rows=request('/'+table+'?portal_receipt_id=eq.'+identity+'&select=lead_id,source_type',token())
        if status!=200 or len(rows)!=1 or rows[0]['source_type']!='online_offer_portal':
            raise AssertionError('Portal intake/source handoff missing')
    admission_checks=verify_portal_admission_http(db,request,token,definition['form_key'],identity,prepared['request_hash'])
    db.query('UPDATE private.acquisition_portal_admission_policy SET enabled=true,network_per_minute=5')
    body=ticket()
    db.query('UPDATE private.acquisition_form_publications SET enabled=false')
    if request(path,service,body)[0]!=403:raise AssertionError('Portal retry ignored revoked publication')
    return ['portal HTTP exact retry and minimal confirmation','portal HTTP receipt evidence and workspace isolation',
      'portal HTTP intake attribution and raw-write denial','portal HTTP disabled and revoked publication denied','verified portal HTTP legacy bypass revoked','verified portal HTTP consumed admission denied']+admission_checks


def verify_portal_admission_http(db,request,token,form_key,submission,request_hash):
    from uuid import uuid4
    from tools.acquisition_portal_admission import PortalAdmission
    service=token(role='service_role');path='/rpc/admit_acquisition_portal_request'
    body={'p_attempt':str(uuid4()),'p_form_key':form_key,'p_network_hash':'a'*64,'p_purpose':'submit',
          'p_submission':submission,'p_request_hash':request_hash}
    db.query('UPDATE private.acquisition_portal_admission_policy SET enabled=false')
    if request(path,service,body)[0]!=403:raise AssertionError('Disabled admission policy accepted')
    db.query("UPDATE private.acquisition_portal_admission_policy SET enabled=true,network_per_minute=1,approval_ref='synthetic-http-policy',valid_from=clock_timestamp()-interval '1 minute',expires_at=clock_timestamp()+interval '1 hour'")
    for caller in (None,token()):
        if request(path,caller,body)[0] not in (401,403):raise AssertionError('Browser can reserve portal admission')
    status,result=request(path,service,body)
    if status!=200:raise AssertionError('Portal admission HTTP failed')
    admission=PortalAdmission.model_validate(result)
    if not admission.admitted or str(admission.attempt_id)!=body['p_attempt'] or admission.form_key!=form_key:
        raise AssertionError('Portal admission identity changed')
    if request(path,service,body)[0]!=409:raise AssertionError('Replayed admission was free capacity')
    status,result=request(path,service,body|{'p_attempt':str(uuid4())})
    denied=PortalAdmission.model_validate(result)
    if status!=200 or denied.admitted:raise AssertionError('Network capacity was not enforced')
    if db.query('SELECT denied_total FROM private.acquisition_portal_admission_totals')[0]['denied_total']!=1:
        raise AssertionError('Admission denial did not commit')
    db.query('UPDATE private.acquisition_portal_admission_policy SET enabled=false')
    if request(path,service,body|{'p_attempt':str(uuid4())})[0]!=403:raise AssertionError('Disabled policy kept admitting')
    if request('/rpc/purge_acquisition_portal_admissions',token(),{})[0]!=403:
        raise AssertionError('Browser can purge private admission history')
    return ['portal admission HTTP disabled and service-only', 'portal admission HTTP typed identity and fresh attempts',
            'portal admission HTTP committed denial and network cap']
