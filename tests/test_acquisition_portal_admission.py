import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
import pytest

from tools.acquisition_portal_admission import admit_portal_request, portal_network_hash

ID=UUID('fd000000-0000-4000-8000-000000000001')
NOW=datetime.now(timezone.utc)

class Store:
    def __init__(self, patch=None, error=None):
        self.calls=[];self.patch=patch or {};self.error=error
    async def request(self, method, path, *, body):
        self.calls.append((method,path,body))
        if self.error:raise self.error
        return {'attempt_id':body['p_attempt'],'form_key':body['p_form_key'],'purpose':body['p_purpose'],
                'admitted':True,'checked_at':NOW.isoformat(),'expires_at':(NOW+timedelta(seconds=30)).isoformat(),
                'retry_after_seconds':0,'policy_revision':2,**self.patch}


def call(store,**kwargs):
    return asyncio.run(admit_portal_request(store,form_key='synthetic',network_hash='a'*64,purpose='submit',
        submission_id=ID,request_hash='b'*64,clock=lambda:NOW,**kwargs))


def test_each_inquiry_retry_reserves_a_fresh_attempt_without_raw_network_or_seller_fields():
    store=Store();first=call(store);second=call(store)
    assert first.attempt_id!=second.attempt_id
    for method,path,body in store.calls:
        assert method=='POST' and path=='rpc/admit_acquisition_portal_request'
        assert body['p_submission']==str(ID) and body['p_request_hash']=='b'*64
        assert set(body)=={'p_attempt','p_form_key','p_network_hash','p_purpose','p_submission','p_request_hash'}


def test_denial_is_no_store_429_with_bounded_retry_hint():
    store=Store({'admitted':False,'expires_at':None,'retry_after_seconds':12})
    with pytest.raises(HTTPException) as error:call(store)
    assert error.value.status_code==429
    assert error.value.headers=={'Cache-Control':'no-store','Retry-After':'12'}


@pytest.mark.parametrize('patch',[
    {'attempt_id':str(ID)},{'form_key':'other'},{'purpose':'display'},{'workspace_id':str(ID)},
    {'admitted':1},{'policy_revision':0},{'policy_revision':True},{'retry_after_seconds':61},
    {'expires_at':None},{'expires_at':(NOW+timedelta(seconds=31)).isoformat()},
    {'checked_at':(NOW-timedelta(seconds=60)).isoformat(),'expires_at':(NOW-timedelta(seconds=30)).isoformat()},
    {'checked_at':(NOW+timedelta(seconds=6)).isoformat(),'expires_at':(NOW+timedelta(seconds=36)).isoformat()},
    {'admitted':False,'expires_at':None,'retry_after_seconds':0},
])
def test_malformed_or_stale_admission_never_confirms_capacity(patch):
    with pytest.raises(HTTPException) as error:call(Store(patch))
    assert error.value.status_code==503 and error.value.headers['Cache-Control']=='no-store'


def test_store_outage_preserves_uncertainty_and_never_retries():
    store=Store(error=HTTPException(503,'Database unavailable'))
    with pytest.raises(HTTPException) as error:call(store)
    assert error.value.status_code==503 and len(store.calls)==1
    assert error.value.headers['Cache-Control']=='no-store'


def test_display_admission_has_no_submission_identity():
    store=Store()
    asyncio.run(admit_portal_request(store,form_key='synthetic',network_hash='a'*64,purpose='display',clock=lambda:NOW))
    assert store.calls[0][2]['p_submission'] is None and store.calls[0][2]['p_request_hash'] is None


@pytest.mark.parametrize('address',['not-an-ip','1.2.3.4,5.6.7.8','fe80::1%en0','https://1.2.3.4',''])
def test_network_identity_rejects_headers_and_invalid_addresses(address):
    with pytest.raises(ValueError):portal_network_hash(address,b'x'*32)


def test_network_hash_normalizes_mapped_ipv4_and_ipv6_networks_without_exposing_address():
    key=b'x'*32
    hashed=portal_network_hash('192.0.2.1',key)
    assert hashed==portal_network_hash('::ffff:192.0.2.1',key)
    assert hashed!=portal_network_hash('192.0.2.2',key)
    assert hashed!=portal_network_hash('192.0.2.1',b'y'*32)
    assert len(hashed)==64 and '192.0.2.1' not in hashed
    assert portal_network_hash('2001:db8:1:2::1',key)==portal_network_hash('2001:db8:1:2::ff',key)
    assert portal_network_hash('2001:db8:1:2::1',key)!=portal_network_hash('2001:db8:1:3::1',key)


@pytest.mark.parametrize('key',[b'short','not-bytes',b'x'*129])
def test_network_hash_requires_a_configured_secret(key):
    with pytest.raises(ValueError):portal_network_hash('192.0.2.1',key)
