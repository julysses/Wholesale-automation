import csv
import io
import zipfile
from datetime import datetime, timezone
from tools.dialer_export import prepare_export

def test_export_keeps_unknown_held_and_excludes_dnc_expired_and_duplicate():
    contact={'id':'c','name':'=formula','phone':'+12145551234','expires_at':'2027-01-01T00:00:00Z','dnc_status':'unknown'}
    lead={'lead_id':'a','address_std':'Test','county':'Collin','dnc':False,'request':{'state':'completed','id':'r'},'contacts':[contact,contact,{**contact,'id':'d','dnc_status':'listed'},{**contact,'id':'e','expires_at':'2020-01-01T00:00:00Z'}]}
    data=prepare_export([lead],datetime(2026,10,15,tzinfo=timezone.utc))
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        rows=list(csv.DictReader(io.StringIO(z.read('contacts-for-review.csv').decode('utf-8-sig'))))
        assert len(rows)==1
        assert rows[0]['CallReady']==rows[0]['SMSReady']=='false'
        assert rows[0]['ContactName']=="'=formula"
        assert rows[0]['Phone']=='12145551234'
        assert len(list(csv.DictReader(io.StringIO(z.read('excluded.csv').decode('utf-8-sig')))))==2
        assert b'not an approved campaign' in z.read('README.txt')

def test_suppressed_incomplete_and_no_result_do_not_export_contacts():
    rows=[{'lead_id':'a','request':{'state':'submitted'}}, {'lead_id':'b','dnc':True,'request':{'state':'completed'}}, {'lead_id':'c','dnc':False,'request':{'state':'completed'},'contacts':[]}]
    with zipfile.ZipFile(io.BytesIO(prepare_export(rows))) as z:
        assert len(z.read('contacts-for-review.csv').decode('utf-8-sig').splitlines())==1
        assert len(z.read('excluded.csv').decode('utf-8-sig').splitlines())==4

from types import SimpleNamespace
from tests.test_trace_operations_api import client_db
from tests.test_offer_review_api import setup, OPERATOR

def test_export_fetches_all_pages_and_requires_admin(client_db):
    client,db,rows=client_db
    items=[{'lead_id':str(i),'request':{'state':'completed'},'dnc':False,'contacts':[]} for i in range(51)]
    db.rpc.return_value.execute.side_effect=[SimpleNamespace(data={'total':51,'items':items[:50]}),SimpleNamespace(data={'total':51,'items':items[50:]})]
    r=client.get('/api/operations/lists/dialer-export',headers={'Authorization':'Bearer test'})
    assert r.status_code==200 and r.headers['cache-control']=='no-store'
    assert [c.args[1]['p_offset'] for c in db.rpc.call_args_list]==[0,50]
    assert all(c.args[1]['p_operator']==OPERATOR for c in db.rpc.call_args_list)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert len(z.read('excluded.csv').decode('utf-8-sig').splitlines())==52
    db.rpc.reset_mock();rows.return_value=SimpleNamespace(data=[{'status':'approved','role':'user'}])
    assert client.get('/api/operations/lists/dialer-export',headers={'Authorization':'Bearer test'}).status_code==403
    db.rpc.assert_not_called()

def test_export_rejects_incomplete_page(client_db):
    client,db,_=client_db
    db.rpc.return_value.execute.return_value=SimpleNamespace(data={'total':51,'items':[]})
    assert client.get('/api/operations/lists/dialer-export',headers={'Authorization':'Bearer test'}).status_code==409
