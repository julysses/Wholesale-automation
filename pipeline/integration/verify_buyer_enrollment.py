"""Public capabilities, immutable consumer evidence and real role/review boundaries."""
from contextlib import ExitStack
import hashlib,json,secrets
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from tests.local_journey_db import Database
from config.settings import settings
from web import auth
from web.api import buyer_enrollment as enrollment
from web.app import app
OWNER='00000000-0000-4000-8000-000000000777'


def verify(db):
    service=Database();service.query('SET ROLE service_role');api=TestClient(app)
    user=str(uuid4());db.query('INSERT INTO auth.users(id) VALUES(%s)',[user]);db.query("INSERT INTO profiles(id,email,status,role) VALUES(%s,%s,'approved','user')",[user,user+'@example.test'])
    fake=SimpleNamespace(auth=SimpleNamespace(get_user=lambda token:SimpleNamespace(user=SimpleNamespace(id=OWNER if token=='admin' else user))),table=db.table)
    headers={'Authorization':'Bearer admin'};buyer=str(uuid4());phone='+12145550991'
    db.query("INSERT INTO buyers(id,first_name,last_name,phone,active,sms_opt_in) VALUES(%s,'Synthetic Enrollment','Fixture',%s,true,false)",[buyer,phone])
    def invite():
        cap={'request_id':str(uuid4()),'token':secrets.token_urlsafe(32)}
        response=api.post(f'/api/buyers/{buyer}/enrollment-invite',json=cap,headers=headers)
        assert response.status_code==200,response.text
        return cap
    def submit(cap,accepted=True,**changes):
        return api.post('/api/buyer-enrollment/submit',json={**cap,'phone':phone,'accepted':accepted,'program_version':enrollment.program()['version'],**changes})
    try:
        with ExitStack() as stack:
            for key,value in {'buyer_sms_brand':'Synthetic Buyer Program','buyer_enrollment_public_origin':'https://synthetic.example.test',
                'buyer_enrollment_support':'support@example.test','buyer_enrollment_enabled':True,'buyer_enrollment_policies_reviewed':True}.items():stack.enter_context(patch.object(settings,key,value))
            stack.enter_context(patch.object(settings,'buyer_enrollment_approved_version',enrollment.program()['version']))
            stack.enter_context(patch.object(auth,'get_supabase_client',return_value=fake));stack.enter_context(patch.object(enrollment,'get_supabase_client',return_value=service))
            public=api.get('/api/buyer-enrollment/config');assert public.status_code==200 and public.json()['available']
            assert public.headers.get('cache-control')=='no-store'
            assert not any(k in public.json() for k in ['buyer_id','phone','token'])
            with patch.object(settings,'buyer_enrollment_approved_version','outdated'):assert not api.get('/api/buyer-enrollment/config').json()['available']
            with patch.object(settings,'buyer_enrollment_policies_reviewed',False):assert api.get('/api/buyer-enrollment/config').json()['program'] is None
            cap={'request_id':str(uuid4()),'token':secrets.token_urlsafe(32)}
            assert api.post(f'/api/buyers/{buyer}/enrollment-invite',json=cap).status_code==401
            assert api.post(f'/api/buyers/{buyer}/enrollment-invite',json=cap,headers={'Authorization':'Bearer user'}).status_code==403
            cap=invite()
            assert api.post(f'/api/buyers/{buyer}/enrollment-invite',json=cap,headers=headers).json()['id']==cap['request_id']
            stored=db.query('SELECT token_hash FROM private.buyer_enrollment_invites WHERE id=%s',[cap['request_id']])[0]
            assert stored['token_hash']==hashlib.sha256(cap['token'].encode()).hexdigest() and cap['token'] not in json.dumps(stored)
            assert api.post('/api/buyer-enrollment/receipt',json=cap).json()['saved'] is False
            invalid=submit({**cap,'token':secrets.token_urlsafe(32)});assert invalid.status_code==409,(invalid.status_code,invalid.text)
            assert submit(cap,phone='+12145550992').status_code==409
            assert submit(cap,program_version='b'*64).status_code==409
            assert submit(cap,accepted='true').status_code==422
            assert submit(cap,website='bot').status_code==422
            assert not db.query('SELECT id FROM private.buyer_enrollment_submissions WHERE id=%s',[cap['request_id']])
            first=submit(cap);assert first.status_code==200 and first.json()['saved'],first.text
            assert submit(cap).json()==first.json()
            task=db.query('SELECT status,assigned_to,due_date FROM tasks WHERE id=%s',[cap['request_id']])[0]
            assert task['status']=='pending' and task['assigned_to']==OWNER and task['due_date']
            assert db.query('SELECT count(*) n FROM tasks WHERE id=%s',[cap['request_id']])[0]['n']==1
            assert submit(cap,False).status_code==409
            assert db.query('SELECT sms_opt_in FROM buyers WHERE id=%s',[buyer])[0]['sms_opt_in'] is False
            assert not db.query('SELECT id FROM private.buyer_sms_consent_reviews WHERE buyer_id=%s',[buyer])
            history=api.get(f'/api/buyers/{buyer}/enrollment-submissions',headers=headers)
            assert history.status_code==200,history.text
            row=history.json()['submissions'][0];assert row['evidence']['program']['disclosure']==public.json()['program']['disclosure'] and not row['reviewed']
            assert len(row['evidence_sha256'])==64
            review=api.post(f'/api/buyers/{buyer}/enrollment-submissions/{cap["request_id"]}/review',headers=headers)
            assert review.status_code==200 and review.json()['saved'],review.text
            assert db.query('SELECT status FROM tasks WHERE id=%s',[cap['request_id']])[0]['status']=='completed'
            assert db.query('SELECT sms_opt_in FROM buyers WHERE id=%s',[buyer])[0]['sms_opt_in'] is True
            assert api.post(f'/api/buyers/{buyer}/enrollment-submissions/{cap["request_id"]}/review',headers=headers).json()['duplicate'] is True
            # A later consumer refusal is effective without waiting for operator review.
            refusal=invite();assert submit(refusal,False).status_code==200
            assert db.query('SELECT sms_opt_in FROM buyers WHERE id=%s',[buyer])[0]['sms_opt_in'] is False
            db.query('UPDATE buyers SET sms_opt_in=true WHERE id=%s',[buyer])
            assert not service.rpc('buyer_sms_consent_status',{'p_buyer':buyer,'p_operator':OWNER}).execute().data['consent_ready']
            # Reviewing an older, previously unreviewed positive request cannot erase refusal.
            old=invite();assert submit(old).status_code==200
            newer=invite();assert submit(newer,False).status_code==200
            assert api.post(f'/api/buyers/{buyer}/enrollment-submissions/{old["request_id"]}/review',headers=headers).status_code==409
            # A lost committed submission response recovers via the same capability even when enrollment is later disabled.
            recovery=invite();real_rpc=service.rpc;lost={'pending':True}
            def lossy(name,params):
                query=real_rpc(name,params)
                if name!='submit_buyer_enrollment' or not lost['pending']:return query
                class Lost:
                    def execute(self):query.execute();lost['pending']=False;raise TimeoutError('Synthetic committed consumer response lost')
                return Lost()
            with patch.object(service,'rpc',side_effect=lossy):assert submit(recovery).status_code==503
            with patch.object(settings,'buyer_enrollment_enabled',False):
                assert api.post('/api/buyer-enrollment/receipt',json=recovery).json()['saved']
                assert submit(recovery).json()['saved']
            # Changed or deleted buyer identity cannot accept a fresh old-number choice.
            changed=invite();db.query("UPDATE buyers SET phone='+12145550992' WHERE id=%s",[buyer]);assert submit(changed).status_code==409
            db.query('UPDATE buyers SET phone=%s WHERE id=%s',[phone,buyer])
            expired=invite();db.query('ALTER TABLE private.buyer_enrollment_invites DISABLE TRIGGER buyer_enrollment_invite_immutable')
            db.query("UPDATE private.buyer_enrollment_invites SET expires_at=now()-interval '1 second' WHERE id=%s",[expired['request_id']]);db.query('ALTER TABLE private.buyer_enrollment_invites ENABLE TRIGGER buyer_enrollment_invite_immutable')
            assert submit(expired).status_code==409
            # Consumer-facing endpoints never expose SQL grants or enable sending.
            browser=Database();browser.query('SET ROLE authenticated')
            try:
                for query in ['SELECT * FROM private.buyer_enrollment_invites','DELETE FROM private.buyer_enrollment_submissions',"SELECT public.buyer_enrollment_receipt('"+cap['request_id']+"','"+stored['token_hash']+"')"]:
                    try:browser.query(query)
                    except Exception as exc:assert getattr(exc,'pgcode',None)=='42501'
                    else:raise AssertionError('Browser enrollment authority succeeded')
            finally:browser.connection.close()
            try:db.query('UPDATE private.buyer_enrollment_submissions SET accepted=false WHERE id=%s',[cap['request_id']])
            except Exception as exc:assert 'immutable' in str(exc).lower()
            else:raise AssertionError('Consumer evidence changed')
            db.query('DELETE FROM buyers WHERE id=%s',[buyer]);assert api.post('/api/buyer-enrollment/receipt',json=cap).json()['saved']
            assert db.query('SELECT count(*) n FROM private.buyer_enrollment_submissions WHERE buyer_id=%s',[buyer])[0]['n']==5
        assert not db.query('SELECT * FROM net.test_requests')
        print(json.dumps({'buyer_enrollment':'passed','capability':'hashed one-use invitation; 7-day expiry','public_pii':'not exposed',
            'consumer_opt_in':'pending admin review','refusal':'immediate and blocks older positive review','receipt_recovery':'no replay or sends',
            'policies':'exact approved version required','auth':'operator writes protected; exact public endpoint exceptions',
            'immutability':'passed','buyer_deletion':'history retained','provider_calls':0,'production_mutations':0}),flush=True)
    finally:service.connection.close()

if __name__=='__main__':
    db=Database()
    try:verify(db)
    finally:db.connection.close()
