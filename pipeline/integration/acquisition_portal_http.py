"""Seller HTTP journey through actual local PostgREST and the disposable database.

Bot responses/runtime are synthetic. The HTTPX transport bridges to the existing
socket-only curl gateway; returned database status and JSON are real.
No TCP destination, hosted credentials, production write or provider call.
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
import httpx


def verify_portal_receiver_http(db, request, token, other, workspace, definition):
    from web.app import app
    from web.api import acquisition_portal_api as api
    from tools import acquisition_portal_submission as submission
    from tools.acquisition_portal_bot import BotConfig
    from tools.acquisition_portal_runtime import PortalRuntime, PortalStore

    identity='99800000-0000-4000-8000-000000000001'
    route='/api/acquisition/portal/'+definition['form_key']
    inquiry={'submission_id':identity,'form_version':'v1','seller':{'name':'Synthetic HTTP seller','email':'seller@example.test'},
        'property':{'address':'123 HTTP Fixture','city':'Dallas','state':'TX','postal_code':'75201','authority':'owner',
                    'condition':'unsure','occupancy':'vacant','timeline':'flexible','motivation':'Synthetic journey','asking_price':None},
        'selections':{'privacy_acknowledged':True,'email_reply_requested':False}}
    envelope={'inquiry':inquiry,'bot_token':'synthetic-receiver-token'}
    db.query("UPDATE private.acquisition_form_publications SET enabled=true,valid_from=clock_timestamp()-interval '1 minute',expires_at=clock_timestamp()+interval '1 hour'")
    db.query("UPDATE private.acquisition_portal_admission_policy SET enabled=true,global_per_minute=100,form_per_minute=100,network_per_minute=20,bot_hostname='seller.example.test',approval_ref='synthetic-receiver-acceptance',valid_from=clock_timestamp()-interval '1 minute',expires_at=clock_timestamp()+interval '1 hour'")
    config=PortalRuntime(BotConfig('synthetic-secret','seller.example.test'),'public-test-key',b'x'*32,
                         'https://fixture.supabase.co',token(role='service_role'))
    committed=[];drop_reply=[True];provider_calls=[]

    class LosingReplyStore(PortalStore):
        async def request(self,method,path,*,body):
            result=await super().request(method,path,body=body)
            if path=='rpc/complete_acquisition_portal_request':
                committed.append((body,result))
                if drop_reply[0]:
                    drop_reply[0]=False
                    raise HTTPException(503,'Synthetic lost reply after actual commit')
            return result

    def gateway(req):
        if req.method!='POST' or req.url.host!='localhost' or req.url.query:
            raise AssertionError('Unexpected receiver gateway request')
        status,body=request(req.url.path,req.headers['authorization'].removeprefix('Bearer '),json.loads(req.content))
        return httpx.Response(status,json=body)

    @asynccontextmanager
    async def store(_):
        async with httpx.AsyncClient(base_url='http://localhost/',
                transport=httpx.MockTransport(gateway),timeout=10,trust_env=False,
                headers={'Authorization':'Bearer '+config.database_key}) as client:
            yield LosingReplyStore(client)

    challenge=datetime.now(timezone.utc).isoformat()
    def provider(req):
        provider_calls.append(req.content)
        return httpx.Response(200,json={'success':True,'hostname':config.bot.hostname,'action':'acquisition_offer',
                                       'cdata':identity,'challenge_ts':challenge})
    actual_verify=submission.verify_portal_bot
    async def verify(bot,**kwargs):
        kwargs['transport']=httpx.MockTransport(provider)
        return await actual_verify(bot,**kwargs)

    with patch.object(api,'configured_portal',return_value=config),patch.object(api,'open_portal_store',store),patch.object(submission,'verify_portal_bot',verify):
        with TestClient(app,client=('192.0.2.45',12345)) as client:
            display=client.get(route)
            if display.status_code!=200 or display.json()!={'definition':definition,'bot_site_key':config.site_key}:
                raise AssertionError('Real seller display projection failed')
            invalid=client.post(route,json=envelope|{'workspace_id':workspace})
            if invalid.status_code!=422 or provider_calls:
                raise AssertionError('Invalid seller routing reached verifier')
            lost=client.post(route,json=envelope)
            if lost.status_code!=503 or len(committed)!=1 or committed[0][1].get('duplicate') is not False:
                raise AssertionError('Seller lost reply did not follow actual database commit')
            retry=client.post(route,json=envelope)
            if retry.status_code!=200 or retry.json()!={'submission_id':identity,'status':'received','duplicate':True}:
                raise AssertionError('Seller exact recovery did not reconcile actual receipt')
            if len(committed)!=2 or committed[0][0]['p_prepared']!=committed[1][0]['p_prepared'] or committed[0][0]['p_attempt']==committed[1][0]['p_attempt']:
                raise AssertionError('Seller retry changed inquiry or reused admission')
            if provider_calls[0]!=provider_calls[1]:
                raise AssertionError('Seller retry changed provider verification identity')
            for response in (display,invalid,lost,retry):
                if response.headers.get('cache-control')!='no-store':
                    raise AssertionError('Seller response may be cached')
            rows=db.query('SELECT lead_id,workspace_id FROM public.lead_form_submissions WHERE id=%s',[identity])
            if len(rows)!=1 or str(rows[0]['workspace_id'])!=workspace:
                raise AssertionError('Seller receipt missing or misrouted')
            for table in ('seller_intakes','acquisition_lead_sources'):
                if db.query('SELECT count(*) AS n FROM public.'+table+' WHERE portal_receipt_id=%s',[identity])[0]['n']!=1:
                    raise AssertionError('Seller retry duplicated or omitted handoff')
            listing='/lead_form_submissions?id=eq.'+identity+'&select=id'
            if request(listing,token(other))!=(200,[]):
                raise AssertionError('Seller receipt exposed to another workspace')
            anonymous_status,anonymous_body=request(listing,None)
            if anonymous_status not in (401,403) and (anonymous_status,anonymous_body)!=(200,[]):
                raise AssertionError('Seller receipt exposed anonymously')
            db.query('UPDATE private.acquisition_form_publications SET enabled=false')
            calls=len(provider_calls)
            revoked=client.post(route,json=envelope)
            if revoked.status_code!=404 or len(provider_calls)!=calls:
                raise AssertionError('Revoked public form reached verification')
    return ['seller receiver actual display and bounded input',
            'seller receiver actual commit loss and exact recovery',
            'seller receiver single intake attribution and tenant isolation',
            'seller receiver publication revocation before provider']
