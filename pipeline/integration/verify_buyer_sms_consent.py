"""Real SQL/API written-consent review boundaries; no provider requests."""
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from tests.local_journey_db import Database
from web import auth
from web.api import buyers_api
from web.app import app

OWNER='00000000-0000-4000-8000-000000000777'

def verify(db):
    service=Database();service.query('SET ROLE service_role')
    user=str(uuid4());buyer=str(uuid4());phone='+12145550731'
    db.query('INSERT INTO auth.users(id) VALUES(%s)',[user])
    db.query("INSERT INTO profiles(id,email,role,status) VALUES(%s,%s,'user','approved')",[user,user+'@example.test'])
    db.query("INSERT INTO buyers(id,first_name,last_name,phone,active,sms_opt_in) VALUES(%s,'Synthetic','Consent',%s,true,true)",[buyer,phone])
    client=TestClient(app)
    fake=SimpleNamespace(auth=SimpleNamespace(get_user=lambda token:SimpleNamespace(user=SimpleNamespace(id=OWNER if token=='admin' else user))),table=db.table)
    reference=str(uuid4())
    body={'request_id':reference,'phone':'(214) 555-0731','source_type':'signed_document','source_url':'https://evidence.example.test/synthetic',
        'sha256':'a'*64,'consented_at':'2026-10-01T10:00:00-05:00','disclosure':'Synthetic written buyer deal alerts consent, not property inquiry consent. Reply STOP to opt out.',
        'affirmative_action':'Synthetic signed buyer request for deal-alert SMS','reviewed_written_evidence':True,'accepted':True}
    def read(token='admin'):
        return client.get(f'/api/buyers/{buyer}/sms-consent',headers={'Authorization':'Bearer '+token})
    def save(value=None,token='admin'):
        return client.post(f'/api/buyers/{buyer}/sms-consent',json=value or body,headers={'Authorization':'Bearer '+token})
    try:
        with patch.object(auth,'get_supabase_client',return_value=fake),patch.object(buyers_api,'_get_supabase',return_value=service):
            assert client.get(f'/api/buyers/{buyer}/sms-consent').status_code==401
            initial=read().json();assert initial['consent_ready'] is False and initial['receipt_id'] is None,initial
            assert read('user').json()['can_review'] is False
            assert save(token='user').status_code==403
            assert save({**body,'reviewed_written_evidence':False}).status_code==422
            assert save({**body,'consented_at':'2099-01-01T00:00:00+00:00'}).status_code==422
            assert save({**body,'consented_at':'2026-10-01T00:00:00'}).status_code==422
            assert save({**body,'source_type':'phone_call'}).status_code==422
            assert save({**body,'source_url':'https://username:password@example.test/x'}).status_code==422
            assert save({**body,'sha256':'missing'}).status_code==422
            result=save();assert result.status_code==200,result.text
            assert result.json()['saved'] and result.json()['id']==reference
            assert save().json()['duplicate'] is True
            assert db.query('SELECT count(*) n FROM private.buyer_sms_consent_reviews WHERE id=%s',[reference])[0]['n']==1
            assert save({**body,'disclosure':body['disclosure']+' Changed'}).status_code==409
            current=read().json();assert current['consent_ready'] and not current['sending_available'] and current['receipt_id']==reference,current
            held=client.post('/api/buyers/outreach/sms',headers={'Authorization':'Bearer admin'},json={
                'request_id':str(uuid4()),'buyer_ids':[buyer],'custom_message':'Synthetic buyer deal alert'}).json()
            assert held['sent_count']==0 and held['skipped_count']==1 and held['outcomes'][0]['reason']=='buyer_sms_route_unavailable',held
            # A committed review with a lost HTTP acknowledgement is recovered by the exact same reference.
            real_rpc=service.rpc; lost={'pending':True}; lost_body={**body,'request_id':str(uuid4())}
            def lossy_rpc(name,params):
                query=real_rpc(name,params)
                if name!='review_buyer_sms_consent' or not lost['pending']:return query
                class Lost:
                    def execute(self):
                        query.execute();lost['pending']=False
                        raise TimeoutError('Synthetic committed review acknowledgement lost')
                return Lost()
            with patch.object(service,'rpc',side_effect=lossy_rpc):
                assert save(lost_body).status_code==503
                recovered=save(lost_body);assert recovered.status_code==200 and recovered.json()['duplicate'] is True,recovered.text
            # Real row changes cannot inherit this destination-bound receipt.
            db.query("UPDATE buyers SET phone='+12145550732' WHERE id=%s",[buyer])
            assert read().json()['consent_ready'] is False
            assert save({**body,'request_id':str(uuid4())}).status_code==409
            db.query('UPDATE buyers SET phone=%s WHERE id=%s',[phone,buyer])
            # Refusal is a later immutable record, not overwriting earlier proof.
            refused={**body,'request_id':str(uuid4()),'accepted':False}
            assert save(refused).status_code==200
            assert not read().json()['consent_ready']
            assert db.query('SELECT sms_opt_in FROM buyers WHERE id=%s',[buyer])[0]['sms_opt_in'] is False
            # Imported/manual booleans cannot override a newer refusal.
            db.query('UPDATE buyers SET sms_opt_in=true WHERE id=%s',[buyer])
            assert not read().json()['consent_ready']
            # A late retry of the old accepted review returns its receipt without changing current refusal.
            assert save().json()['duplicate'] is True
            assert not read().json()['consent_ready']
            db.query("INSERT INTO dnc_registry(id,phone_number,reason,source) VALUES(%s,'214-555-0731','opt_out','synthetic')",[str(uuid4())])
            assert read().json()['suppressed'] is True
            assert save({**body,'request_id':str(uuid4())}).status_code==409
            # Real-browser roles cannot write/delete/forge receipts or invoke the service RPC.
            browser=Database();browser.query('SET ROLE authenticated')
            try:
                for sql in ['SELECT * FROM private.buyer_sms_consent_reviews','DELETE FROM private.buyer_sms_consent_reviews',
                    "SELECT public.buyer_sms_consent_status('"+buyer+"','"+OWNER+"')"]:
                    try:browser.query(sql)
                    except Exception as exc:assert getattr(exc,'pgcode',None)=='42501',str(exc)
                    else:raise AssertionError('Browser consent access succeeded')
            finally:browser.connection.close()
            # Even a privileged direct update is stopped by the immutable trigger.
            try:db.query('UPDATE private.buyer_sms_consent_reviews SET accepted=false WHERE id=%s',[reference])
            except Exception as exc:assert 'immutable' in str(exc).lower(),str(exc)
            else:raise AssertionError('Consent history mutation succeeded')
            db.query('DELETE FROM buyers WHERE id=%s',[buyer])
            assert db.query('SELECT count(*) n FROM private.buyer_sms_consent_reviews WHERE buyer_id=%s',[buyer])[0]['n']==3
            assert read().status_code==404
        print(json.dumps({'buyer_sms_consent':'passed','storage':'real SQL','operator_auth':'verified','admin_only_review':True,
            'legacy_boolean':'insufficient','exact_retry':'immutable receipt','changed_phone':'unready','later_refusal':'retained and enforced',
            'suppression':'cannot clear','deletion_retention':'passed','browser_access':'denied','sending_activation':False,'provider_calls':0}),flush=True)
    finally:service.connection.close()

if __name__=='__main__':
    db=Database()
    try:verify(db)
    finally:db.connection.close()
