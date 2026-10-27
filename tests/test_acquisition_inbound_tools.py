import copy
import pytest

from tools.acquisition_inbound_tools import prepare_inbound_tool
from tools.acquisition_intake import prepare_facebook_intake

ROUTE = dict(workspace_id='10000000-0000-4000-8000-000000000001',
    integration_id='96000000-0000-4000-8000-000000000001',agent_id='agent_test',
    agent_version=3,acquisition_number='+12145550100')
ANSWERS = dict(property_address='123 Main St',city='Dallas',state='TX',authority='yes',
    condition='repairs needed',timeline='30 days',motivation='moving',asking_price='$150,000',phone='2145550101')


def payload(name='submit_seller_intake'):
    args={'request_id':'20000000-0000-4000-8000-000000000001','expected_revision':0}
    if name=='submit_seller_intake': args['answers']=dict(ANSWERS)
    elif name=='request_callback': args.update(phone='2145550101',preferred_time='tomorrow afternoon',purpose='discuss property',requested_by_caller=True)
    else: args.update(reason='caller_requested',details='Please let me talk to a person',requested_by_caller=True)
    return {'name':name,'args':args,'call':{'call_id':'call_test','agent_id':'agent_test','agent_version':3,
        'call_type':'phone_call','direction':'inbound','to_number':'+12145550100','call_status':'ongoing',
        'transcript':'PRIVATE TRANSCRIPT','from_number':'+12145550999','metadata':{'workspace_id':'untrusted'}}}


def prepare(value): return prepare_inbound_tool(value,**ROUTE)


def test_shared_intake_semantics_without_fabricated_facebook_source():
    inbound=prepare(payload())
    facebook=prepare_facebook_intake(leadgen_id='123',provider_data={'id':'123','field_data':[
        {'name':key,'values':[ANSWERS[key]]} for key in sorted(ANSWERS)]})
    assert all(inbound['prepared'][key]==facebook[key] for key in inbound['prepared'])
    assert inbound['prepared']['asking_price']=='150000.00'
    assert inbound['prepared']['classification']=='requires_human_review'
    assert 'facebook' not in str(inbound)
    assert 'PRIVATE TRANSCRIPT' not in str(inbound) and '+12145550999' not in str(inbound)
    assert inbound['workspace_id']==ROUTE['workspace_id']
    assert inbound['execution_authorized'] is False


def test_stable_request_hash_ignores_transcript_but_detects_answer_revision_and_scope_changes():
    data=payload(); first=prepare(data)
    data['call']['transcript']='changed';data['call']['metadata']={'workspace_id':'another'}
    data['args']['answers']=dict(reversed(list(ANSWERS.items())))
    assert prepare(data)==first
    for key,value in [('expected_revision',1),('request_id','20000000-0000-4000-8000-000000000002')]:
        changed=copy.deepcopy(data);changed['args'][key]=value
        assert prepare(changed)['request_hash']!=first['request_hash']
    data['args']['answers']['asking_price']='175000'
    assert prepare(data)['request_hash']!=first['request_hash']
    assert prepare_inbound_tool(payload(),**{**ROUTE,'workspace_id':'10000000-0000-4000-8000-000000000002'})['request_hash']!=first['request_hash']


@pytest.mark.parametrize('value',[None,'','150k','150-175000'])
def test_missing_or_ambiguous_price_does_not_become_zero(value):
    data=payload()
    if value is None: del data['args']['answers']['asking_price']
    else: data['args']['answers']['asking_price']=value
    result=prepare(data)['prepared']
    assert result['asking_price'] is None
    assert result['classification']!='qualified'


@pytest.mark.parametrize('name',['request_callback','request_human'])
def test_requests_have_no_execution_or_permission(name):
    result=prepare(payload(name))
    assert result['prepared']['status']=='review_required'
    assert result['contact_permission_granted'] is False
    assert result['execution_authorized'] is False
    if name=='request_callback':
        assert result['prepared']['scheduled_at'] is None
        assert result['prepared']['phone_verified'] is False
        assert result['prepared']['eligibility_required'] is True
    else: assert result['prepared']['transfer_authorized'] is False


@pytest.mark.parametrize('key,value',[('workspace_id','other'),('lead_id','other'),('approved',True),
    ('expected_revision',True),('expected_revision',-1),('expected_revision',1000000000),('request_id','bad')])
def test_model_cannot_supply_scope_authority_or_invalid_revision(key,value):
    data=payload();data['args'][key]=value
    with pytest.raises(ValueError):prepare(data)


@pytest.mark.parametrize('field,value',[('call_status','ended'),('call_status','registered'),('direction','outbound'),
    ('agent_id','other'),('agent_version',4),('to_number','+12145550199')])
def test_exact_ongoing_inbound_call_required(field,value):
    data=payload();data['call'][field]=value
    with pytest.raises(ValueError):prepare(data)


@pytest.mark.parametrize('answers',[{},None,{'transcript':'content'},{'price':'10'},
    {'asking_price':100},{'property_address':'x'*2001},{'contact_permission_granted':'true'}])
def test_bounded_strict_answer_fields(answers):
    data=payload();data['args']['answers']=answers
    with pytest.raises(ValueError):prepare(data)


@pytest.mark.parametrize('name',['request_callback','request_human'])
@pytest.mark.parametrize('assertion',[False,'true',1,None])
def test_requested_actions_need_explicit_boolean(name,assertion):
    data=payload(name);data['args']['requested_by_caller']=assertion
    with pytest.raises(ValueError):prepare(data)


def test_system_escalation_can_be_requested_without_false_caller_attribution():
    data=payload('request_human');data['args'].update(reason='unsupported_language',requested_by_caller=False)
    assert prepare(data)['evidence']['requested_by_caller'] is False


def test_callback_never_uses_caller_id_as_fallback():
    data=payload('request_callback');data['args']['phone']=''
    with pytest.raises(ValueError):prepare(data)


@pytest.mark.parametrize('change',[{'name':'execute_offer'},{'extra':'ignored?'},{'call':None}])
def test_unsupported_envelope_rejected(change):
    data=payload();data.update(change)
    with pytest.raises(ValueError):prepare(data)


def test_callback_normalizes_explicit_number_without_claiming_verification():
    data=payload('request_callback')
    assert prepare(data)['prepared']['normalized_phone']=='+12145550101'
    data['args']['phone']='call my sister'
    result=prepare(data)
    assert result['evidence']['phone']=='call my sister'
    assert result['prepared']['normalized_phone'] is None
    assert 'PHONE_NORMALIZATION_REVIEW_REQUIRED' in result['prepared']['reason_codes']
