"""Real SQL/auth/signed callbacks with a stubbed, non-retrying Twilio create boundary."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime
import json
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlencode,urlsplit,parse_qs
from uuid import uuid4,NAMESPACE_URL,uuid5
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator
from twilio.base.exceptions import TwilioRestException
from tests.local_journey_db import Database
from config.settings import settings
from tools import buyer_sms
from web import auth
from web.api import buyers_api,buyer_twilio_webhooks,twilio_webhooks
from web.api.buyer_outreach import dispatch
from web.app import app
OWNER='00000000-0000-4000-8000-000000000777'
ACCOUNT='AC'+'1'*32;SERVICE='MG'+'2'*32;CAMPAIGN='CM'+'3'*32
SENDER='+12145550010';PRIMARY='+12145550000';TOKEN='synthetic-buyer-token-not-a-credential'
BASE='https://synthetic.example.test';BRAND='Synthetic Buyer Program'
BODY=BRAND+': Synthetic buyer deal alert.\n'+buyer_sms.FOOTER


def verify(db):
    service=Database();service.query('SET ROLE service_role')
    api=TestClient(app);callback_api=TestClient(app)
    calls=[];sids={};mode={'value':'accepted'};next_phone={'value':100}
    fake=SimpleNamespace(auth=SimpleNamespace(get_user=lambda _:SimpleNamespace(user=SimpleNamespace(id=OWNER))),table=db.table)
    def buyer(label,phone=None,consent=True):
        identity=str(uuid4());next_phone['value']+=1
        phone=phone or '+1214555'+str(next_phone['value']).zfill(4)
        service.table('buyers').insert({'id':identity,'first_name':label,'last_name':'Synthetic','active':True,'sms_opt_in':True,'phone':phone}).execute()
        if consent:
            service.rpc('review_buyer_sms_consent',{'p_id':str(uuid4()),'p_buyer':identity,'p_operator':OWNER,'p_phone':phone,'p_accepted':True,
                'p_evidence':{'source_type':'signed_document','source_url':'https://evidence.example.test/synthetic','sha256':'a'*64,
                'consented_at':'2026-10-01T10:00:00-05:00','disclosure':'Synthetic written buyer deal-alert consent, not homeowner inquiry consent. Reply STOP.',
                'affirmative_action':'Synthetic written buyer choice','reviewed_written_evidence':True}}).execute()
        return identity,phone
    def submit(ids,reference=None,**changes):
        return api.post('/api/buyers/outreach/sms',headers={'Authorization':'Bearer synthetic'},json={
            'request_id':reference or str(uuid4()),'buyer_ids':ids,'custom_message':BODY,**changes})
    def request_callback(kind,payload,reference=None,valid=True,native=False):
        path=('/webhooks/twilio/' if native else '/webhooks/buyer-twilio/')+kind
        if reference:path+='?message_id='+reference
        payload={'AccountSid':ACCOUNT,**payload}
        signature=RequestValidator(TOKEN).compute_signature(BASE+path,payload) if valid else 'invalid'
        return callback_api.post(path,content=urlencode(payload),headers={'Content-Type':'application/x-www-form-urlencoded','X-Twilio-Signature':signature})
    def delivery(reference,phone,state='delivered',**extra):
        return request_callback('status',{'MessageSid':sids[reference],'From':SENDER,'To':phone,'MessageStatus':state,'MessagingServiceSid':SERVICE,**extra},reference)
    def reply(phone,text,identity=None,**extra):
        sid=identity or 'SM'+uuid4().hex
        return request_callback('inbound',{'MessageSid':sid,'From':phone,'To':SENDER,'Body':text,'MessagingServiceSid':SERVICE,**extra}),sid
    def provider(**kwargs):
        calls.append(kwargs)
        reference=parse_qs(urlsplit(kwargs['status_callback']).query)['message_id'][0]
        sids[reference]='SM'+uuid4().hex
        if mode['value'] in {'early','early_optout'}:
            assert delivery(reference,kwargs['to']).status_code==200
            if mode['value']=='early_optout':raise TwilioRestException(400,'synthetic',code=21610,msg='Synthetic contradictory opt-out rejection')
            raise TimeoutError('Synthetic create acknowledgement lost after delivered callback')
        if mode['value']=='unknown':raise TimeoutError('Synthetic create result lost')
        if mode['value']=='optout':raise TwilioRestException(400,'synthetic',code=21610,msg='Synthetic recipient opt-out')
        return SimpleNamespace(sid=sids[reference])
    http=[]
    def client(*_args,**kwargs):
        http.append(kwargs['http_client']);return SimpleNamespace(messages=SimpleNamespace(create=provider))
    patches={'sms_live_enabled':True,'buyer_sms_live_enabled':True,'twilio_account_sid':ACCOUNT,'twilio_auth_token':TOKEN,
        'twilio_from_number':PRIMARY,'twilio_messaging_service_sid':'MG'+'9'*32,'twilio_webhook_base_url':BASE,
        'buyer_sms_service_sid':SERVICE,'buyer_sms_campaign_sid':CAMPAIGN,'buyer_sms_from_number':SENDER,'buyer_sms_brand':BRAND,
        'sms_allowed_recipients':''}
    try:
        with ExitStack() as stack:
            for key,value in patches.items():stack.enter_context(patch.object(settings,key,value))
            stack.enter_context(patch.object(auth,'get_supabase_client',return_value=fake))
            stack.enter_context(patch.object(buyers_api,'_get_supabase',return_value=service))
            stack.enter_context(patch.object(buyer_twilio_webhooks,'get_supabase_client',return_value=service))
            stack.enter_context(patch.object(twilio_webhooks,'get_supabase_client',return_value=service))
            stack.enter_context(patch.object(twilio_webhooks,'notify_reply',return_value={'status':'not_required'}))
            stack.enter_context(patch.object(twilio_webhooks,'queue_app_reply',return_value=False))
            stack.enter_context(patch.object(twilio_webhooks,'reply_redirect',return_value=None))
            stack.enter_context(patch.object(buyer_sms,'_texas_now',return_value=datetime(2026,10,22,12,tzinfo=ZoneInfo('America/Chicago'))))
            stack.enter_context(patch('twilio.rest.Client',side_effect=client))
            assert api.get('/api/buyers/outreach/sms/readiness').status_code==401
            assert not buyer_sms.readiness(service)['available']
            db.query('INSERT INTO private.buyer_sms_routes(service_sid,account_sid,campaign_sid,from_number,brand,approved_at,enabled,scope,proof) VALUES(%s,%s,%s,%s,%s,now(),true,%s,%s)',
                [SERVICE,ACCOUNT,CAMPAIGN,SENDER,BRAND,'buyer_deal_alerts',json.dumps({'synthetic':True})])
            assert buyer_sms.readiness(service)['available']
            with patch.object(settings,'buyer_sms_live_enabled',False):assert not buyer_sms.readiness(service)['available']
            with patch.object(settings,'buyer_sms_from_number',PRIMARY):assert not buyer_sms.readiness(service)['available']
            missing,phone=buyer('NoWrittenConsent',consent=False)
            assert submit([missing]).json()['skipped_count']==1 and not calls
            target,phone=buyer('Delivery');campaign=str(uuid4());first=submit([target],campaign)
            assert first.status_code==200,first.text
            result=first.json();assert result['sent_count']==1,result
            reference=result['outcomes'][0]['message_id'];assert len(calls)==1
            assert calls[0]['body']==BODY and calls[0]['from_']==SENDER and calls[0]['messaging_service_sid']==SERVICE
            assert all(client.timeout==5 for client in http)
            assert submit([target],campaign).json()['sent_count']==1 and len(calls)==1
            assert submit([target],campaign,custom_message=BODY+' changed').json()['unknown_count']==1 and len(calls)==1
            assert request_callback('status',{'MessageSid':sids[reference],'From':SENDER,'To':phone,'MessageStatus':'delivered'},reference,valid=False).status_code==401
            assert delivery(reference,'+12145559999').status_code==503
            assert delivery(reference,phone,From=PRIMARY).status_code==403
            db.query('UPDATE private.buyer_sms_routes SET enabled=false WHERE service_sid=%s',[SERVICE])
            with patch.object(settings,'sms_live_enabled',False),patch.object(settings,'buyer_sms_live_enabled',False):
                assert delivery(reference,phone).status_code==200
            db.query('UPDATE private.buyer_sms_routes SET enabled=true WHERE service_sid=%s',[SERVICE])
            assert delivery(reference,phone,'queued').status_code==200
            assert db.query('SELECT status FROM buyer_outreach_log WHERE id=%s',[reference])[0]['status']=='delivered'
            assert delivery(reference,phone,'undelivered').status_code==200
            assert delivery(reference,phone).status_code==200
            assert db.query('SELECT status FROM buyer_outreach_log WHERE id=%s',[reference])[0]['status']=='unknown'
            # Human reply handoff is atomic/idempotent, without AI or outbound replies.
            returned,sid=reply(phone,'Please send details');assert returned.status_code==200,returned.text
            event=str(uuid5(NAMESPACE_URL,f'buyer-twilio:{ACCOUNT}:inbound:{sid}'))
            task=db.query('SELECT buyer_id,assigned_to,status,due_date FROM tasks WHERE id=%s',[event])[0]
            assert task['buyer_id']==target and task['assigned_to']==OWNER and task['status']=='pending' and task['due_date']
            assert reply(phone,'Please send details',sid)[0].status_code==200
            assert db.query('SELECT count(*) n FROM tasks WHERE id=%s',[event])[0]['n']==1
            assert reply(phone,'STOP',OptOutType='STOP')[0].status_code==200
            assert db.query('SELECT sms_opt_in FROM buyers WHERE id=%s',[target])[0]['sms_opt_in'] is False
            assert db.query('SELECT status FROM tasks WHERE id=%s',[event])[0]['status']=='cancelled'
            assert reply(phone,'START',OptOutType='START')[0].status_code==200
            assert db.query('SELECT sms_opt_in FROM buyers WHERE id=%s',[target])[0]['sms_opt_in'] is False
            # Native inquiry STOP also suppresses a buyer; its route remains independent.
            native,native_phone=buyer('NativeStop')
            native_result=request_callback('inbound',{'MessageSid':'SM'+uuid4().hex,'From':native_phone,'To':PRIMARY,'Body':'STOP'},native=True)
            assert native_result.status_code==200,native_result.text
            assert db.query('SELECT sms_opt_in FROM buyers WHERE id=%s',[native])[0]['sms_opt_in'] is False
            # Unknown submission stops the batch and later campaigns for that number.
            uncertain,uphone=buyer('Unknown');later,_=buyer('Unattempted');before=len(calls);mode['value']='unknown'
            uncertain_result=submit([uncertain,later]).json();assert uncertain_result['unknown_count']==1 and uncertain_result['unattempted_count']==1,uncertain_result
            uncertain_ref=uncertain_result['outcomes'][0]['message_id'];assert len(calls)==before+1
            assert submit([uncertain]).json()['unattempted_count']==1 and len(calls)==before+1
            assert delivery(uncertain_ref,uphone).status_code==200
            mode['value']='accepted'
            assert submit([uncertain]).json()['skipped_count']==1 and len(calls)==before+1
            # Callback-first delivery survives a subsequent create timeout.
            early,ephone=buyer('Early');mode['value']='early';early_result=submit([early]).json()
            assert early_result['sent_count']==1 and early_result['outcomes'][0]['status']=='delivered',early_result
            mode['value']='early_optout';contradictory,cphone=buyer('ContradictoryProviderRejection')
            contradiction=submit([contradictory]).json()
            assert contradiction['unknown_count']==1 and db.query('SELECT id FROM dnc_registry WHERE phone_number=%s',[cphone]),contradiction
            mode['value']='accepted'
            # Lost committed reservation and authorization never authorize SDK replay.
            actual_rpc=service.rpc
            for function in ['claim_buyer_sms','authorize_buyer_sms_submission']:
                lost_target,_=buyer(function);lost={'pending':True};reference_id=str(uuid4());before=len(calls)
                def lossy(name,params):
                    query=actual_rpc(name,params)
                    if name!=function or not lost['pending']:return query
                    class Lost:
                        def execute(self):query.execute();lost['pending']=False;raise TimeoutError('Synthetic committed response lost')
                    return Lost()
                with patch.object(service,'rpc',side_effect=lossy):
                    assert submit([lost_target],reference_id).json()['unknown_count']==1
                assert submit([lost_target],reference_id).json()['unknown_count']==1 and len(calls)==before
            for committed in [False,True]:
                recovered,_=buyer('ResultReceiptRecovery');lost={'pending':True};campaign_ref=str(uuid4());before=len(calls)
                def uncertain_result(name,params):
                    query=actual_rpc(name,params)
                    if name!='record_buyer_sms_outcome' or not lost['pending']:return query
                    class LostResult:
                        def execute(self):
                            lost['pending']=False
                            if committed:query.execute()
                            raise TimeoutError('Synthetic result persistence response lost')
                    return LostResult()
                with patch.object(service,'rpc',side_effect=uncertain_result):
                    recovered_result=submit([recovered],campaign_ref).json()
                    assert recovered_result['sent_count']==1,recovered_result
                assert len(calls)==before+1 and submit([recovered],campaign_ref).json()['sent_count']==1 and len(calls)==before+1
            # A STOP committed after reservation but before final authorization prevents create.
            stopped,sphone=buyer('StoppedBeforeAuthorization');before=len(calls)
            def stop_before_authorize(name,params):
                if name=='authorize_buyer_sms_submission':
                    service.table('dnc_registry').insert({'id':str(uuid4()),'phone_number':sphone,'reason':'opt_out','source':'synthetic'}).execute()
                return actual_rpc(name,params)
            with patch.object(service,'rpc',side_effect=stop_before_authorize):assert submit([stopped]).json()['skipped_count']==1
            assert len(calls)==before
            # Log failure rolls back all three reservation records before any provider call.
            invalid,_=buyer('InvalidDeal');before=len(calls)
            assert submit([invalid],deal_id=str(uuid4())).json()['unknown_count']==1 and len(calls)==before
            assert not db.query('SELECT id FROM private.buyer_sms_messages WHERE buyer_id=%s',[invalid])
            # Same destination in two buyer records cannot receive duplicate campaign messages.
            shared,shared_phone=buyer('SharedFirst');shared_two,_=buyer('SharedSecond',phone=shared_phone);before=len(calls)
            shared_result=submit([shared,shared_two]).json();assert shared_result['sent_count']==1 and shared_result['skipped_count']==1 and len(calls)==before+1,shared_result
            # Eight distinct DB sessions contend on one request; one transport create wins.
            concurrent,_=buyer('Concurrent');barrier=Barrier(8);before=len(calls);request=buyers_api.OutreachRequest(request_id=uuid4(),buyer_ids=[concurrent],custom_message=BODY)
            def worker(_):
                local=Database();local.query('SET ROLE service_role')
                try:barrier.wait(timeout=10);return dispatch(local,OWNER,request,'sms')
                finally:local.connection.close()
            with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(worker,range(8)))
            assert len(calls)==before+1,results
            assert db.query('SELECT count(*) n FROM private.buyer_sms_messages WHERE buyer_id=%s',[concurrent])[0]['n']==1
            # Known opt-out rejection persists DNC, without fabricating a provider SID.
            rejected,rphone=buyer('OptOutRejection');mode['value']='optout';rejected_result=submit([rejected]).json();mode['value']='accepted'
            assert rejected_result['failed_count']==1,rejected_result
            assert db.query('SELECT sms_opt_in FROM buyers WHERE id=%s',[rejected])[0]['sms_opt_in'] is False
            assert db.query('SELECT provider_sid FROM private.buyer_sms_messages WHERE buyer_id=%s',[rejected])[0]['provider_sid'] is None
            assert db.query('SELECT id FROM dnc_registry WHERE phone_number=%s',[rphone])
            # Buyer deletion keeps status/reply correlation and original snapshot.
            deleted,dphone=buyer('Deleted');deleted_result=submit([deleted]).json();deleted_ref=deleted_result['outcomes'][0]['message_id']
            db.query('DELETE FROM buyers WHERE id=%s',[deleted]);assert delivery(deleted_ref,dphone).status_code==200
            assert reply(dphone,'Still interested')[0].status_code==200
            assert db.query('SELECT buyer_id,buyer_snapshot FROM buyer_outreach_log WHERE id=%s',[deleted_ref])[0]['buyer_id'] is None
            # Owner loss is visible; carrier retry recovers assignment without resending SMS.
            recover,ophone=buyer('OwnerRecovery');submit([recover]);db.query("UPDATE profiles SET status='suspended' WHERE id=%s",[OWNER])
            response,owner_sid=reply(ophone,'Please call');assert response.status_code==503,response.text
            db.query("UPDATE profiles SET status='approved' WHERE id=%s",[OWNER]);assert reply(ophone,'Please call',owner_sid)[0].status_code==200
            owner_event=str(uuid5(NAMESPACE_URL,f'buyer-twilio:{ACCOUNT}:inbound:{owner_sid}'))
            assert db.query('SELECT assigned_to FROM tasks WHERE id=%s',[owner_event])[0]['assigned_to']==OWNER
            browser=Database();browser.query('SET ROLE authenticated')
            try:
                for query in ['SELECT * FROM private.buyer_sms_routes',"UPDATE private.buyer_sms_messages SET status='delivered'",
                    'DELETE FROM private.buyer_sms_events',"SELECT public.buyer_sms_route_status('{}'::jsonb)"]:
                    try:browser.query(query)
                    except Exception as exc:assert getattr(exc,'pgcode',None)=='42501',str(exc)
                    else:raise AssertionError('Browser buyer SMS authority succeeded')
            finally:browser.connection.close()
            try:db.query('UPDATE private.buyer_sms_messages SET body=%s WHERE id=%s',['Changed',deleted_ref])
            except Exception as exc:assert 'immutable' in str(exc).lower(),str(exc)
            else:raise AssertionError('SMS message identity changed')
            before=len(calls)
            assert api.post('/api/buyers/outreach/'+deleted_result['request_id']+'/reconcile',headers={'Authorization':'Bearer synthetic'}).json()['provider_calls']==0
            assert len(calls)==before
        print(json.dumps({'buyer_sms_transport':'passed','schema':'real SQL','sdk':'stubbed create; 5s timeout; no retries',
            'signed_callback':'bound to account/sender/destination/reference/SID','late_acceptance':'cannot regress delivery','terminal_conflicts':'held',
            'lost_reservation_and_authorization':'no provider replay','stop_before_submission':'blocked','native_stop':'buyer suppressed',
            'reply_tasks':'atomic assigned and duplicate safe','start':'does not clear DNC','daily_limit':1,'shared_destination':'one campaign send',
            'concurrent_sessions':8,'concurrent_dispatches':1,'deletion_retention':'passed','owner_recovery':'receipt retry without send',
            'real_provider_calls':0,'production_mutations':0}),flush=True)
    finally:service.connection.close()

if __name__=='__main__':
    db=Database()
    try:verify(db)
    finally:db.connection.close()
