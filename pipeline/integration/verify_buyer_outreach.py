"""Real buyer dispatch latches/native email claims and signed callback propagation."""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier, local
import time
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from tests.local_journey_db import Database
from config.settings import settings
from tools.email_client import EmailClient
from web import auth
from web.api import buyers_api, sendgrid_webhooks
from web.api.buyer_outreach import dispatch
from web.app import app

OWNER='00000000-0000-4000-8000-000000000777'


def verify(db):
    service=Database();service.query('SET ROLE service_role')
    api=TestClient(app);sent=[];mode={'unknown':False};context=local()
    auth_client=SimpleNamespace(auth=SimpleNamespace(get_user=lambda token:SimpleNamespace(user=SimpleNamespace(id=OWNER))),table=db.table)
    key=ec.generate_private_key(ec.SECP256R1())
    public=base64.b64encode(key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)).decode()
    def buyer(label,**values):
        identity=str(uuid4())
        service.table('buyers').insert({'id':identity,'first_name':label,'last_name':'Synthetic','active':True,
            'sms_opt_in':True,'phone':'+12145550199','email_opt_in':True,'email':label.lower()+'@example.test',**values}).execute()
        return identity
    def submit(ids,reference=None,channel='email',**changes):
        return api.post('/api/buyers/outreach/'+channel,headers={'Authorization':'Bearer synthetic'},json={
            'request_id':reference or str(uuid4()),'buyer_ids':ids,'custom_subject':'Reviewed subject','custom_message':'Reviewed <copy>\nSecond line',**changes})
    def provider(client,*_args,**_kwargs):
        sent.append(client.message_id);time.sleep(0.02)
        if mode['unknown']:return False
        client._provider_message_id='provider-'+client.message_id
        return True
    def callback(identity,email,event='delivered',sid=None,valid=True):
        body=json.dumps([{'sg_event_id':str(uuid4()),'app_message_id':identity,'email':email,'event':event,
            'timestamp':int(time.time()),'sg_message_id':sid or 'separate-event-'+identity}]).encode()
        timestamp=str(int(time.time()))
        signature=base64.b64encode(key.sign(timestamp.encode()+body,ec.ECDSA(hashes.SHA256()))).decode() if valid else 'invalid'
        return api.post('/webhooks/sendgrid/events',content=body,headers={'content-type':'application/json',
            'X-Twilio-Email-Event-Webhook-Signature':signature,'X-Twilio-Email-Event-Webhook-Timestamp':timestamp})
    try:
        with patch.object(auth,'get_supabase_client',return_value=auth_client),patch.object(buyers_api,'_get_supabase',return_value=service),\
             patch('tools.crm.get_supabase_client',side_effect=lambda:getattr(context,'db',service)),\
             patch.object(sendgrid_webhooks,'get_supabase_client',return_value=service),\
             patch.object(settings,'email_live_enabled',True),patch.object(settings,'email_provider','sendgrid'),\
             patch.object(settings,'from_email','sender@example.test'),patch.object(settings,'sendgrid_api_key','synthetic-not-a-key'),\
             patch.object(settings,'email_allowed_recipients',''),patch.object(settings,'sendgrid_webhook_public_key',public),\
             patch.object(EmailClient,'_dispatch',provider):
            target=buyer('Dispatch');campaign=str(uuid4())
            first=submit([target],campaign);assert first.status_code==200,first.text
            result=first.json();assert result['sent_count']==1,result
            identity=result['outcomes'][0]['message_id'];assert sent==[identity]
            assert submit([target],campaign).json()['sent_count']==1 and sent==[identity]
            changed=submit([target],campaign,custom_message='Changed copy').json()
            assert changed['unknown_count']==1 and sent==[identity]
            log=db.query('SELECT body,provider_msg_id,provider_submission_id,status FROM buyer_outreach_log WHERE id=%s',[identity])[0]
            assert '&lt;copy&gt;' in log['body'] and log['provider_msg_id'] is None and log['provider_submission_id']=='provider-'+identity and log['status']=='accepted'
            assert callback(identity,'dispatch@example.test',valid=False).status_code==401
            assert callback(identity,'wrong@example.test').status_code==200
            assert db.query('SELECT status FROM buyer_outreach_log WHERE id=%s',[identity])[0]['status']=='accepted'
            assert callback(identity,'dispatch@example.test',event='open').status_code==200
            assert db.query('SELECT status FROM buyer_outreach_log WHERE id=%s',[identity])[0]['status']=='accepted'
            delivered=callback(identity,'dispatch@example.test');assert delivered.status_code==200,delivered.text
            assert db.query('SELECT status FROM buyer_outreach_log WHERE id=%s',[identity])[0]['status']=='delivered'
            assert submit([target],campaign).json()['sent_count']==1 and len(sent)==1
            assert callback(identity,'dispatch@example.test',event='processed').status_code==200
            assert db.query('SELECT status FROM buyer_outreach_log WHERE id=%s',[identity])[0]['status']=='delivered'
            assert callback(identity,'dispatch@example.test',event='bounce').status_code==200
            assert db.query('SELECT status FROM buyer_outreach_log WHERE id=%s',[identity])[0]['status']=='unknown'
            blocked=submit([target]).json();assert blocked['skipped_count']==1 and len(sent)==1  # bounce suppression

            # A failed initial log insert rolls back its private claim before
            # any external submission (use a missing FK to inject the failure).
            audit_failure=buyer('AuditFailureDispatch');before=len(sent)
            rejected=submit([audit_failure],deal_id=str(uuid4())).json()
            assert rejected['unknown_count']==1 and len(sent)==before
            rejected_id=rejected['outcomes'][0]['message_id']
            assert not db.query('SELECT id FROM private.buyer_outreach_attempts WHERE id=%s',[rejected_id])
            assert not db.query('SELECT id FROM buyer_outreach_log WHERE id=%s',[rejected_id])

            foreign=str(uuid4());db.query('INSERT INTO auth.users VALUES(%s)',[foreign])
            db.query("INSERT INTO profiles(id,email,role,status) VALUES(%s,'foreign-outreach@example.test','user','approved')",[foreign])
            foreign_auth=SimpleNamespace(auth=SimpleNamespace(get_user=lambda token:SimpleNamespace(user=SimpleNamespace(id=foreign))),table=db.table)
            with patch.object(auth,'get_supabase_client',return_value=foreign_auth):
                assert submit([target],campaign).json()['unknown_count']==1
            assert len(sent)==before

            sms=submit([buyer('NoBuyerSms')],channel='sms').json()
            assert sms['skipped_count']==1 and sms['outcomes'][0]['reason']=='buyer_sms_route_unavailable'
            assert len(sent)==1

            # Unknown native email outcome halts the in-flight batch. Future
            # campaigns to that mailbox are held, never treated as failed/retried.
            uncertain=buyer('UnknownDispatch');later=buyer('LaterDispatch');mode['unknown']=True
            uncertain_campaign=str(uuid4());unknown=submit([uncertain,later],uncertain_campaign).json()
            assert unknown['unknown_count']==1 and unknown['unattempted_count']==1 and unknown['failed_count']==0,unknown
            unknown_id=unknown['outcomes'][0]['message_id'];before=len(sent)
            assert submit([uncertain],uncertain_campaign).json()['unknown_count']==1 and len(sent)==before
            assert submit([uncertain]).json()['unattempted_count']==1 and len(sent)==before
            mode['unknown']=False
            assert callback(unknown_id,'unknowndispatch@example.test').status_code==200
            assert submit([uncertain],uncertain_campaign).json()['sent_count']==1 and len(sent)==before

            # Native acceptance survives a lost finish acknowledgment; replay
            # recovers the existing result without another provider invocation.
            loss=buyer('LossDispatch');loss_campaign=str(uuid4());original=service.rpc
            def lose_result(name,params):
                call=original(name,params)
                if name!='finish_buyer_outreach':return call
                def execute():call.execute();raise TimeoutError('Synthetic finish acknowledgment loss')
                return SimpleNamespace(execute=execute)
            with patch.object(service,'rpc',side_effect=lose_result):lost=submit([loss],loss_campaign).json()
            assert lost['unknown_count']==1 and lost['log_failed_count']==1
            before=len(sent);assert submit([loss],loss_campaign).json()['sent_count']==1 and len(sent)==before

            before_finish=buyer('BeforeFinishDispatch');before_campaign=str(uuid4())
            def before_result(name,params):
                if name=='finish_buyer_outreach':raise TimeoutError('Synthetic failure before outcome write')
                return original(name,params)
            with patch.object(service,'rpc',side_effect=before_result):before_loss=submit([before_finish],before_campaign).json()
            before=len(sent);pending_id=before_loss['outcomes'][0]['message_id']
            assert db.query('SELECT status FROM buyer_outreach_log WHERE id=%s',[pending_id])[0]['status']=='submitting'
            recovered=api.post('/api/buyers/outreach/'+before_campaign+'/reconcile',headers={'Authorization':'Bearer synthetic'})
            assert recovered.status_code==200 and recovered.json()['provider_calls']==0,recovered.text
            assert db.query('SELECT status FROM buyer_outreach_log WHERE id=%s',[pending_id])[0]['status']=='accepted'
            assert len(sent)==before
            with patch.object(auth,'get_supabase_client',return_value=foreign_auth):
                assert api.post('/api/buyers/outreach/'+before_campaign+'/reconcile',headers={'Authorization':'Bearer synthetic'}).status_code==404

            # Losing the initial durable claim never authorizes dispatch on retry.
            no_dispatch=buyer('LostClaimDispatch');claim_campaign=str(uuid4())
            def lose_claim(name,params):
                call=original(name,params)
                if name!='claim_buyer_outreach':return call
                def execute():call.execute();raise TimeoutError('Synthetic claim acknowledgment loss')
                return SimpleNamespace(execute=execute)
            before=len(sent)
            with patch.object(service,'rpc',side_effect=lose_claim):assert submit([no_dispatch],claim_campaign).json()['unknown_count']==1
            assert submit([no_dispatch],claim_campaign).json()['unknown_count']==1 and len(sent)==before

            # Deleting a buyer retains both immutable attempt identity and saved
            # destination/name/message/receipt history, without a dangling FK.
            db.query('DELETE FROM buyers WHERE id=%s',[loss])
            retained=db.query('SELECT buyer_id,buyer_snapshot,provider_msg_id,provider_submission_id FROM buyer_outreach_log WHERE id=%s',[lost['outcomes'][0]['message_id']])[0]
            assert retained['buyer_id'] is None and retained['buyer_snapshot']['id']==loss and retained['provider_submission_id']
            assert db.query('SELECT buyer_id FROM private.buyer_outreach_attempts WHERE id=%s',[lost['outcomes'][0]['message_id']])[0]['buyer_id']==loss

            concurrent=buyer('RaceDispatch');reference=uuid4();sessions=[Database() for _ in range(8)];barrier=Barrier(8)
            before=len(sent)
            try:
                for connection in sessions:connection.query('SET ROLE service_role')
                def attempt(connection):
                    context.db=connection;barrier.wait(timeout=10)
                    return dispatch(connection,OWNER,buyers_api.OutreachRequest(request_id=reference,buyer_ids=[concurrent],custom_subject='Race',custom_message='Identical reviewed copy'),'email')
                with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(attempt,sessions))
                assert len(sent)==before+1
                assert all(r['sent_count']+r['unknown_count']==1 for r in results)
            finally:
                for connection in sessions:connection.connection.close()

            # Approved browsers can read, but cannot forge/delete delivery history.
            browser=Database()
            try:
                browser.query('SET ROLE authenticated')
                browser.query("SELECT set_config('request.jwt.claim.sub',%s,false)",[OWNER])
                assert browser.query('SELECT count(*) n FROM buyer_outreach_log')[0]['n']>0
                for statement in ['DELETE FROM buyer_outreach_log','UPDATE buyer_outreach_log SET status=\'delivered\'']:
                    try:browser.query(statement)
                    except Exception as exc:assert getattr(exc,'pgcode',None)=='42501'
                    else:raise AssertionError('Browser forged history')
            finally:browser.connection.close()
        print(json.dumps({'buyer_outreach':'passed','native_email_claim':'real SQL','signed_sendgrid_callback':'verified and bound','provider_submission_vs_event_ids':'separate identifiers; no prefix guessing',
            'duplicate_campaign':'one dispatch','changed_content':'held','lost_claim':'no provider call or takeover',
            'lost_finish':'recovered without repeat','unknown_outcome':'halts batch and future mailbox submissions',
            'contradictory_receipts':'review hold','buyer_sms':'inquiry-only route unavailable','deletion_retention':'passed',
            'browser_history_writes':'denied','concurrent_sessions':8,'concurrent_provider_dispatches':1,
            'provider_transport':'stubbed','real_provider_calls':0}),flush=True)
    finally:service.connection.close()


if __name__=='__main__':
    db=Database()
    try:verify(db)
    finally:db.connection.close()
