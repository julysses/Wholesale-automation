from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from tools import retell_reply_routing as route

PHONE = '+12145550198'

@pytest.fixture
def ready(monkeypatch):
    monkeypatch.setenv('RETELL_SMS_REPLY_ROUTING_ENABLED','true')
    monkeypatch.setenv('RETELL_SMS_FROM_NUMBER','+14698049920')
    monkeypatch.setattr(route,'activation_ready',lambda: True)
    monkeypatch.setattr(route.settings,'sms_allowed_recipients',PHONE)
    monkeypatch.setattr(route.SMSClient,'_in_allowed_hours',lambda _: True)
    monkeypatch.setattr(route,'sms_consent_blocker',lambda *args: None)
    db=MagicMock()
    query=db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value
    query.execute.return_value.data=[{'lead_id':'lead-1','chat_id':'chat-1'}]
    data={'From':PHONE,'To':'+14698049920','Body':'Tomorrow works'}
    receipt={'saved':True,'duplicate':False,'suppressed':False,'opt_out':False,'lead_id':'lead-1'}
    return db,data,receipt,query


def test_known_consented_chat_handoff(ready):
    db,data,receipt,_=ready
    assert route.reply_redirect(db,data,receipt)==route.RETELL_REPLY_URL

@pytest.mark.parametrize('text',['STOP','Stop!','HELP','START','UNSTOP','YES','Please remove me',"Don't text me",'Wrong number'])
def test_controls_never_forward(ready,text):
    db,data,receipt,_=ready;data['Body']=text
    assert route.reply_redirect(db,data,receipt) is None
    db.table.assert_not_called()

@pytest.mark.parametrize('field,value',[('saved',False),('duplicate',True),('suppressed',True),('opt_out',True),('lead_id',None)])
def test_receipt_holds(ready,field,value):
    db,data,receipt,_=ready;receipt[field]=value
    assert route.reply_redirect(db,data,receipt) is None

@pytest.mark.parametrize('jobs',[[],[{'lead_id':'other','chat_id':'chat-1'}],[{'lead_id':'lead-1','chat_id':None}],
    [{'lead_id':'lead-1','chat_id':'one'},{'lead_id':'lead-1','chat_id':'two'}]])
def test_missing_ambiguous_or_wrong_chat_held(ready,jobs):
    db,data,receipt,query=ready;query.execute.return_value.data=jobs
    assert route.reply_redirect(db,data,receipt) is None


def test_all_sending_switches_and_consent_apply(ready,monkeypatch):
    db,data,receipt,_=ready
    monkeypatch.setattr(route,'activation_ready',lambda: False)
    assert route.reply_redirect(db,data,receipt) is None
    monkeypatch.setattr(route,'activation_ready',lambda: True)
    monkeypatch.setattr(route,'sms_consent_blocker',lambda *args: 'revoked')
    assert route.reply_redirect(db,data,receipt) is None
    monkeypatch.setattr(route,'sms_consent_blocker',lambda *args: None)
    monkeypatch.delenv('RETELL_SMS_REPLY_ROUTING_ENABLED')
    assert route.reply_redirect(db,data,receipt) is None


def test_carrier_control_marker_overrides_ordinary_body(ready):
    db,data,receipt,_=ready;data['OptOutType']='STOP'
    assert route.reply_redirect(db,data,receipt) is None


def test_app_owned_chat_never_redirects_to_native_even_if_chat_id_is_present(ready):
    db,data,receipt,query=ready
    query.execute.return_value.data[0]['delivery_transport']='app_twilio'
    assert route.reply_redirect(db,data,receipt) is None
