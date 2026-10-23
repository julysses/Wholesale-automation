"""Buyer-only runtime policy: no provider SDK/network calls."""
from contextlib import ExitStack
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo
import pytest
from config.settings import settings
from tools import buyer_sms

@pytest.fixture
def configured_buyer_route():
    values={'sms_live_enabled':True,'buyer_sms_live_enabled':True,'twilio_account_sid':'AC'+'1'*32,'twilio_auth_token':'synthetic-not-a-key',
        'twilio_webhook_base_url':'https://example.test','twilio_from_number':'+12145550000','twilio_messaging_service_sid':'MG'+'9'*32,
        'buyer_sms_service_sid':'MG'+'2'*32,'buyer_sms_campaign_sid':'CM'+'3'*32,'buyer_sms_from_number':'+12145550010',
        'buyer_sms_brand':'Synthetic Buyer Program','sms_allowed_recipients':'','tcpa_allowed_start_hour':9,'tcpa_allowed_end_hour':19,'sms_weekend_blocked':True}
    with ExitStack() as stack:
        for key,value in values.items():stack.enter_context(patch.object(settings,key,value))
        stack.enter_context(patch.object(buyer_sms,'_texas_now',return_value=datetime(2026,10,22,12,tzinfo=ZoneInfo('America/Chicago'))))
        yield

@pytest.mark.parametrize('when,expected',[
    ('2026-10-22T08:59:59','outside_sending_hours'),('2026-10-22T09:00:00',''),('2026-10-22T18:59:59',''),
    ('2026-10-22T19:00:00','outside_sending_hours'),('2026-10-24T12:00:00','weekend_sending_disabled'),('2026-10-25T12:00:00','weekend_sending_disabled')])
def test_buyer_sms_texas_window(configured_buyer_route,when,expected):
    body='Synthetic Buyer Program: Reviewed deal.\n'+buyer_sms.FOOTER
    with patch.object(buyer_sms,'_texas_now',return_value=datetime.fromisoformat(when).replace(tzinfo=ZoneInfo('America/Chicago'))):
        assert buyer_sms.preflight('+12145550111',body)==expected

@pytest.mark.parametrize('setting,value',[
    ('buyer_sms_live_enabled',False),('sms_live_enabled',False),('twilio_auth_token',''),('buyer_sms_campaign_sid',''),
    ('buyer_sms_service_sid','MG'+'9'*32),('buyer_sms_from_number','+12145550000'),('buyer_sms_brand','')])
def test_buyer_sms_cannot_fall_back_to_homeowner_route(configured_buyer_route,setting,value):
    with patch.object(settings,setting,value):assert buyer_sms.configuration_hold()=='buyer_sms_route_unavailable'

@pytest.mark.parametrize('body',['Unbranded message','Synthetic Buyer Program: Missing opt-out','Synthetic Buyer Program: '+'a'*1600+'\n'+buyer_sms.FOOTER])
def test_full_reviewed_sms_needs_brand_footer_and_bounded_length(configured_buyer_route,body):
    assert buyer_sms.preflight('+12145550111',body)=='buyer_sms_copy_requires_review'

def test_buyer_launch_allowlist_remains_enforced(configured_buyer_route):
    body='Synthetic Buyer Program: Reviewed deal.\n'+buyer_sms.FOOTER
    with patch.object(settings,'sms_allowed_recipients','+12145550111'):
        assert buyer_sms.preflight('(214) 555-0111',body)==''
        assert buyer_sms.preflight('+12145550222',body)=='sms_recipient_not_allowed'

@pytest.mark.parametrize('result',[None,{},True,{'approved':'true'},{'approved':False}])
def test_sender_readiness_requires_confirmed_database_approval(configured_buyer_route,result):
    db=SimpleNamespace(rpc=lambda *_args:SimpleNamespace(execute=lambda:SimpleNamespace(data=result)))
    assert buyer_sms.readiness(db)['available'] is False
