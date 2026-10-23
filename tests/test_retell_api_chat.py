from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import requests
from tools.retell_api_chat import RetellAPIChat, ChatOutcomeUncertain, ChatReviewRequired, agent_texts

OP='00000000-0000-4000-8000-000000000001'
LEAD='00000000-0000-4000-8000-000000000002'
AGENT='agent_synthetic'

@pytest.fixture(autouse=True)
def verified_api_chat(monkeypatch):
    get=Mock(return_value=response(session(),200))
    monkeypatch.setattr('tools.retell_api_chat.requests.get',get)
    return get

def client():
    return RetellAPIChat('test-secret', AGENT, 2)

def reply(messages=None):
    return {'messages': messages if messages is not None else [{'message_id':'msg_1','role':'agent','content':'Thanks. Julio will follow up.'}]}

def response(data, status=201):
    return SimpleNamespace(status_code=status,json=lambda:data)

def session(**patch):
    return {'chat_id':'chat_test','agent_id':AGENT,'version':2,'chat_type':'api_chat','chat_status':'ongoing',
            'metadata':{'operation_id':OP,'lead_id':LEAD,'transport':'wholesaleos_twilio'},**patch}

def test_create_binds_generation_only_session_to_numeric_release_and_operation(monkeypatch):
    post=Mock(return_value=response(session(message_with_tool_calls=[{'role':'agent','content':'Do not send this startup transcript'}])))
    monkeypatch.setattr('tools.retell_api_chat.requests.post',post)
    assert client().create(OP,LEAD)=='chat_test'
    assert post.call_count==1
    url=post.call_args.args[0];args=post.call_args.kwargs
    assert url=='https://api.retellai.com/create-chat'
    assert args['json']=={'agent_id':AGENT,'agent_version':2,'metadata':session()['metadata']}
    assert args['allow_redirects'] is False
    assert args['timeout']==(5,20)

@pytest.mark.parametrize('patch',[{'version':3},{'version':True},{'chat_type':'sms_chat'},{'metadata':{}},
    {'agent_id':'agent_wrong'},{'chat_status':'ended'},{'chat_id':''},{'chat_id':'../../other'}])
def test_mismatched_creation_is_uncertain_never_retried(monkeypatch,patch):
    post=Mock(return_value=response(session(**patch)));monkeypatch.setattr('tools.retell_api_chat.requests.post',post)
    with pytest.raises(ChatOutcomeUncertain):client().create(OP,LEAD)
    assert post.call_count==1

@pytest.mark.parametrize('version',['latest','latest_published','2',None,True,-1,1000000000])
def test_unpinned_release_rejected_before_provider(version):
    with pytest.raises(ValueError):RetellAPIChat('key',AGENT,version)

def test_actual_recipient_text_preserved_exactly_and_generation_not_delivery(monkeypatch):
    post=Mock(return_value=response(reply()));monkeypatch.setattr('tools.retell_api_chat.requests.post',post)
    text='  I can talk Friday.\nIs that possible? '
    generated=client().complete('chat_test',text,OP,LEAD)
    assert post.call_args.args[0]=='https://api.retellai.com/create-chat-completion'
    assert post.call_args.kwargs['json']=={'chat_id':'chat_test','content':text}
    assert generated[0].message_id=='msg_1'
    assert generated[0].content=='Thanks. Julio will follow up.'
    assert not hasattr(generated[0],'delivered')

@pytest.mark.parametrize('status',[200,301,302,307,400,401,402,429,500,503])
def test_noncreated_status_is_uncertain_and_not_retried_or_redirected(monkeypatch,status):
    post=Mock(return_value=response({'error':'secret provider data'},status));monkeypatch.setattr('tools.retell_api_chat.requests.post',post)
    with pytest.raises(ChatOutcomeUncertain) as exc:client().complete('chat_test','Real reply',OP,LEAD)
    assert 'secret' not in str(exc.value)
    assert post.call_count==1
    assert post.call_args.kwargs['allow_redirects'] is False

@pytest.mark.parametrize('failure',[requests.Timeout('secret'),requests.ConnectionError('secret'),ValueError('secret')])
def test_ambiguous_network_or_json_failure_is_redacted_and_never_replayed(monkeypatch,failure):
    post=Mock(side_effect=failure);monkeypatch.setattr('tools.retell_api_chat.requests.post',post)
    with pytest.raises(ChatOutcomeUncertain) as exc:client().complete('chat_test','Real reply',OP,LEAD)
    assert 'secret' not in str(exc.value);assert exc.value.__suppress_context__;assert post.call_count==1

@pytest.mark.parametrize('messages',[None,[],[None],[{'role':'user','content':'echo','message_id':'u'}],
    [{'role':'tool_call_result','content':'private result','message_id':'tool'}],
    [{'role':'agent','content':'Hi','message_id':'a'},{'role':'tool_call_invocation','name':'end_call'}],
    [{'role':'agent','content':'Hi'}],[{'role':'agent','content':'','message_id':'a'}],
    [{'role':'agent','content':'A'*1601,'message_id':'a'}],
    [{'role':'agent','content':'Hi','message_id':'a','multimedia':[{'url':'https://example.com/private'}]}],
    [{'role':'agent','content':'Hi\x00','message_id':'a'}],
    [{'role':'agent','content':'one','message_id':'a'},{'role':'agent','content':'two','message_id':'a'}],
    [{'role':'agent','content':'a'*900,'message_id':'a'},{'role':'agent','content':'b'*900,'message_id':'b'}]])
def test_unsafe_or_unidentifiable_outputs_hold_the_entire_turn(messages):
    with pytest.raises(ChatReviewRequired):agent_texts(messages)

def test_ordered_agent_messages_preserve_identifiers_and_text_without_truncation():
    messages=[{'role':'agent','content':' First. ','message_id':'a'}, {'role':'agent','content':'Second\nline.','message_id':'b'}]
    assert [(m.message_id,m.content) for m in agent_texts(messages)]==[('a',' First. '),('b','Second\nline.')]

@pytest.mark.parametrize('text',[None,'','   ','a'*1601])
def test_missing_actual_input_cannot_be_fabricated(monkeypatch,text):
    post=Mock();monkeypatch.setattr('tools.retell_api_chat.requests.post',post)
    with pytest.raises(ValueError):client().complete('chat_test',text,OP,LEAD)
    post.assert_not_called()

@pytest.mark.parametrize('patch',[{'chat_type':'sms_chat'},{'chat_id':'chat_other'},{'metadata':{}},{'version':3},{'chat_status':'ended'},{'agent_id':'agent_other'}])
def test_existing_session_must_be_bound_api_chat_before_completion(monkeypatch,verified_api_chat,patch):
    verified_api_chat.return_value=response(session(**patch),200)
    post=Mock();monkeypatch.setattr('tools.retell_api_chat.requests.post',post)
    with pytest.raises(ChatOutcomeUncertain):client().complete('chat_test','Real reply',OP,LEAD)
    post.assert_not_called()
    assert verified_api_chat.call_args.kwargs['allow_redirects'] is False

@pytest.mark.parametrize('text',['STOP','stop!',' HELP ','START','UNSTOP','YES','INFO','OPT OUT','Please stop texting me'])
def test_control_messages_never_reach_generation(monkeypatch,verified_api_chat,text):
    post=Mock();monkeypatch.setattr('tools.retell_api_chat.requests.post',post)
    with pytest.raises(ChatReviewRequired):client().complete('chat_test',text,OP,LEAD)
    post.assert_not_called();verified_api_chat.assert_not_called()

@pytest.mark.parametrize('status',[301,401,404,429,500])
def test_failed_session_lookup_cannot_generate(monkeypatch,verified_api_chat,status):
    verified_api_chat.return_value=response({},status)
    post=Mock();monkeypatch.setattr('tools.retell_api_chat.requests.post',post)
    with pytest.raises(ChatOutcomeUncertain):client().complete('chat_test','Real reply',OP,LEAD)
    post.assert_not_called()


def test_live_agent_version_schema_creates_and_completes_without_legacy_field(monkeypatch, verified_api_chat):
    live = session(); live['agent_version'] = live.pop('version')
    post = Mock(side_effect=[response(live), response(reply())])
    monkeypatch.setattr('tools.retell_api_chat.requests.post', post)
    verified_api_chat.return_value = response(live, 200)
    chat_id = client().create(OP, LEAD)
    assert client().complete(chat_id, 'Please call ASAP', OP, LEAD)[0].message_id == 'msg_1'
    assert post.call_count == 2


@pytest.mark.parametrize('patch', [
    {'agent_version': 3}, {'agent_version': True}, {'agent_version': '2'},
    {'agent_version': 2, 'version': 3}, {'agent_version': 2, 'version': True},
    {'agent_version': None},
])
def test_live_version_invalid_or_conflicting_alias_stays_held(monkeypatch, patch):
    live = session(); live.pop('version'); live.update(patch)
    post = Mock(return_value=response(live))
    monkeypatch.setattr('tools.retell_api_chat.requests.post', post)
    with pytest.raises(ChatOutcomeUncertain): client().create(OP, LEAD)
    assert post.call_count == 1


@pytest.mark.parametrize('failure', ['http200','timeout','shape'])
def test_completed_history_reconciles_without_second_post(monkeypatch, verified_api_chat, failure):
    before = session(message_with_tool_calls=[])
    after = session(message_with_tool_calls=[
        {'role':'user','message_id':'u1','content':'Please call'},
        {'role':'agent','message_id':'a1','content':'What time works?'}])
    verified_api_chat.side_effect = [response(before,200),response(after,200)]
    post = Mock(side_effect=requests.Timeout() if failure=='timeout' else None,
                return_value=response({} if failure=='shape' else reply(),200 if failure=='http200' else 201))
    monkeypatch.setattr('tools.retell_api_chat.requests.post',post)
    assert client().complete('chat_test','Please call',OP,LEAD)[0].content == 'What time works?'
    assert post.call_count == 1
    assert verified_api_chat.call_count == 2

@pytest.mark.parametrize('change', ['no_reply','wrong_input','tool','long','duplicate','prior_changed','wrong_chat','other_user'])
def test_read_only_reconciliation_rejects_ambiguous_or_unsafe_history(monkeypatch, verified_api_chat, change):
    prior = [{'role':'agent','message_id':'a0','content':'Welcome'}]
    history = prior + [{'role':'user','message_id':'u1','content':'Please call'},
                       {'role':'agent','message_id':'a1','content':'What time works?'}]
    after = session(message_with_tool_calls=history)
    if change=='no_reply': history.pop()
    if change=='wrong_input': history[1]['content']='Another input'
    if change=='tool': history[2]['role']='tool_call_invocation'
    if change=='long': history[2]['content']='x'*199
    if change=='duplicate': history[2]['message_id']='a0'
    if change=='prior_changed': history[0]={'role':'agent','message_id':'a0','content':'Changed'}
    if change=='wrong_chat': after['chat_id']='chat_other'
    if change=='other_user': history.append({'role':'user','message_id':'u2','content':'Again'})
    verified_api_chat.side_effect=[response(session(message_with_tool_calls=prior),200),response(after,200)]
    post=Mock(return_value=response({},200));monkeypatch.setattr('tools.retell_api_chat.requests.post',post)
    with pytest.raises(ChatOutcomeUncertain):client().complete('chat_test','Please call',OP,LEAD)
    assert post.call_count==1
