import copy
import itertools
import json
import pytest
from tools.acquisition_inbound_events import project_inbound_event, reconcile_inbound_lifecycle

CONFIG=dict(workspace_id='10000000-0000-4000-8000-000000000001',integration_id='20000000-0000-4000-8000-000000000001',agent_id='agent_test',agent_version=3,acquisition_number='+12145550100')

def payload(event='call_started'):
    return {'event':event,'call':{'call_id':'call_test','agent_id':'agent_test','agent_version':3,'direction':'inbound','call_type':'phone_call','to_number':CONFIG['acquisition_number'],'from_number':'+12145550999','call_status':'ongoing' if event=='call_started' else 'ended','start_timestamp':1000,**({} if event=='call_started' else {'end_timestamp':5000})}}

def project(value): return project_inbound_event(value,**CONFIG)

def test_allowlist_drops_sensitive_data_and_untrusted_scope():
    value=payload('call_analyzed');value['call'].update(transcript='private seller words',recording_url='https://private.test/audio',call_analysis={'owner_name':'private name'},metadata={'workspace_id':'attacker','lead_id':'attacker'},retell_llm_dynamic_variables={'phone':'private phone'})
    row=project(value);encoded=json.dumps(row)
    assert row['sensitive_content_present'] is True
    for secret in ['private seller','private.test','private name','private phone','attacker','12145550999','12145550100']: assert secret not in encoded
    assert row['workspace_id']==CONFIG['workspace_id'] and row['execution_authorized'] is False
    assert value['call']['transcript']=='private seller words'

@pytest.mark.parametrize('patch',[{'direction':'outbound'},{'call_type':'web_call'},{'agent_id':'other'},{'agent_version':True},{'agent_version':4},{'to_number':'+12145550200'},{'start_timestamp':True},{'start_timestamp':-1},{'start_timestamp':'1000'},{'call_id':'x\nsecret'},{'call_status':'mystery'},{'end_timestamp':5000}])
def test_rejects_wrong_route_and_malformed_metadata(patch):
    value=payload();value['call'].update(patch)
    with pytest.raises(ValueError):project(value)

@pytest.mark.parametrize('event',['transcript_updated','chat_started','transfer_started','transfer_bridged','transfer_cancelled','transfer_ended','retell.call.started','unknown'])
def test_unsupported_events_do_not_collapse_multiple_transfers(event):
    with pytest.raises(ValueError,match='UNSUPPORTED_INBOUND_EVENT'):project(payload(event))

def test_retries_and_out_of_order_events_have_one_monotonic_result():
    rows=[project(payload(event)) for event in ['call_started','call_ended','call_analyzed']]
    expected=reconcile_inbound_lifecycle(rows)
    assert expected['state']=='ended' and expected['qualification_status']=='not_evaluated'
    assert expected['permitted_actions']==[] and expected['execution_authorized'] is False
    for order in itertools.permutations(rows):assert reconcile_inbound_lifecycle(list(order)+[rows[0]])==expected

def test_terminal_event_does_not_require_started_or_invent_success():
    value=payload('call_ended');value['call'].update(call_status='not_connected',start_timestamp=None,end_timestamp=None)
    result=reconcile_inbound_lifecycle([project(value)])
    assert result['state']=='not_connected' and result['analysis_event_received'] is False

def test_error_and_missing_analysis_do_not_qualify_seller():
    value=payload('call_ended');value['call']['call_status']='error'
    assert reconcile_inbound_lifecycle([project(value)])['state']=='failed'
    assert reconcile_inbound_lifecycle([project(payload())])['state']=='in_progress'

def test_conflicting_same_event_retry_is_review_in_both_orders():
    one=payload('call_ended');two=copy.deepcopy(one);two['call']['end_timestamp']=6000
    rows=[project(one),project(two)]
    assert reconcile_inbound_lifecycle(rows)==reconcile_inbound_lifecycle(rows[::-1])
    assert reconcile_inbound_lifecycle(rows)['reason_codes']==['CONFLICTING_CALL_TIMESTAMPS','CONFLICTING_EVENT_RETRY']

def test_conflicting_terminal_status_and_time_require_review():
    one=payload('call_ended');two=payload('call_analyzed');two['call'].update(call_status='error',end_timestamp=6000)
    result=reconcile_inbound_lifecycle([project(one),project(two)])
    assert result['state']=='review'
    assert result['reason_codes']==['CONFLICTING_CALL_TIMESTAMPS','CONFLICTING_TERMINAL_STATUS']

def test_scope_and_mutated_projections_are_rejected():
    one=project(payload());two=project_inbound_event(payload(),**(CONFIG|{'workspace_id':'30000000-0000-4000-8000-000000000001'}))
    with pytest.raises(ValueError,match='MIXED_CALL_SCOPE'):reconcile_inbound_lifecycle([one,two])
    for patch in [{'call_status':'ended'},{'execution_authorized':True},{'direction':'outbound'},{'transcript':'private'},{'projection_hash':'bad'}]:
        with pytest.raises(ValueError):reconcile_inbound_lifecycle([one|patch])

def test_no_unbounded_or_empty_reconciliation():
    for rows in [[],[project(payload())]*101,None]:
        with pytest.raises(ValueError):reconcile_inbound_lifecycle(rows)


def test_conflicting_retry_and_terminal_reconciliation_is_order_independent():
    first=payload('call_ended');changed=copy.deepcopy(first);changed['call']['end_timestamp']=6000
    rows=[project(first),project(changed),project(payload('call_analyzed'))]
    expected=reconcile_inbound_lifecycle(rows)
    for order in itertools.permutations(rows):assert reconcile_inbound_lifecycle(list(order))==expected

@pytest.mark.parametrize('field,value',[('event',[]),('event',{}),('call_status',[]),('call_status',{})])
def test_unhashable_provider_values_are_validation_errors(field,value):
    body=payload()
    if field=='event':body[field]=value
    else:body['call'][field]=value
    with pytest.raises(ValueError):project(body)
