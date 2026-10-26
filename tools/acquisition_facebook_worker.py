"""One leased native inquiry per invocation. No outreach, scheduler or legacy path."""
import hashlib
import hmac
import json
import os
import re
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from tools.acquisition_intake import prepare_facebook_intake

FIELDS = 'id,created_time,form_id,field_data,custom_disclaimer_responses,ad_id,adset_id,campaign_id,is_organic,platform'


class WorkerUnavailable(RuntimeError):
    pass


class ProviderFailure(Exception):
    def __init__(self, outcome, reason):
        self.outcome, self.reason = outcome, reason
        super().__init__(reason)


def _configuration():
    if os.getenv('ACQUISITION_ENABLED','').lower() != 'true' or os.getenv('ACQUISITION_FACEBOOK_WORKER_ENABLED','').lower() != 'true':
        raise WorkerUnavailable('Facebook worker disabled')
    config={name:os.getenv('ACQUISITION_FACEBOOK_'+name,'').strip() for name in
            ('WORKER_SERVICE_KEY','PAGE_TOKEN','APP_SECRET','PAGE_ID','INTEGRATION_ID','GRAPH_VERSION')}
    url=os.getenv('SUPABASE_URL','').rstrip('/')
    try:
        parsed=urlsplit(url); parsed.port
        config['INTEGRATION_ID']=str(UUID(config['INTEGRATION_ID']))
        valid=(all(config.values()) and re.fullmatch(r'[0-9]{1,200}',config['PAGE_ID'])
               and re.fullmatch(r'v[0-9]{1,2}\.0',config['GRAPH_VERSION'])
               and parsed.scheme=='https' and parsed.hostname and not any((parsed.path,parsed.query,parsed.fragment,parsed.username,parsed.password)))
    except ValueError:
        valid=False
    if not valid:
        raise WorkerUnavailable('Facebook worker configuration unavailable')
    config['url']=url
    return config


async def _rpc(client,name,body):
    if name not in ('claim_acquisition_events','complete_facebook_acquisition_intake','defer_acquisition_event'):
        raise WorkerUnavailable('Unsupported worker operation')
    try:
        response=await client.post('rpc/'+name,json=body)
        if response.status_code!=200:
            raise WorkerUnavailable('Worker database operation unconfirmed')
        return response.json()
    except (httpx.HTTPError,ValueError):
        raise WorkerUnavailable('Worker database operation unconfirmed') from None


async def _retrieve(client,config,lead_id):
    proof=hmac.new(config['APP_SECRET'].encode(),config['PAGE_TOKEN'].encode(),hashlib.sha256).hexdigest()
    try:
        async with client.stream('GET',f"https://graph.facebook.com/{config['GRAPH_VERSION']}/{lead_id}",
                                 params={'fields':FIELDS,'appsecret_proof':proof},
                                 headers={'Authorization':'Bearer '+config['PAGE_TOKEN']}) as response:
            raw=bytearray()
            async for chunk in response.aiter_bytes():
                if len(raw)+len(chunk)>524288:
                    raise ProviderFailure('review','INVALID_PROVIDER_DATA')
                raw.extend(chunk)
            try:
                data=json.loads(raw)
            except (ValueError,UnicodeDecodeError):
                data=None
            error=data.get('error') if isinstance(data,dict) else None
            code=error.get('code') if isinstance(error,dict) else None
            if response.status_code==429 or code in (4,17,32,613):
                raise ProviderFailure('retry','PROVIDER_RATE_LIMIT')
            if response.status_code==401 or code in (102,190):
                raise ProviderFailure('review','CREDENTIALS_INVALID')
            if response.status_code==403 or code in (10,200):
                raise ProviderFailure('review','PERMISSION_DENIED')
            if response.status_code>=500:
                raise ProviderFailure('retry','PROVIDER_UNAVAILABLE')
            if response.status_code!=200 or error is not None or not isinstance(data,dict):
                raise ProviderFailure('review','INVALID_PROVIDER_DATA')
            return data
    except httpx.TimeoutException:
        raise ProviderFailure('retry','PROVIDER_TIMEOUT') from None
    except httpx.HTTPError:
        raise ProviderFailure('retry','PROVIDER_UNAVAILABLE') from None


async def process_facebook_inquiry():
    config=_configuration()
    key=config['WORKER_SERVICE_KEY']
    async with httpx.AsyncClient(base_url=config['url']+'/rest/v1/',timeout=10.0,follow_redirects=False,
                                headers={'apikey':key,'Authorization':'Bearer '+key}) as database:
        claims=await _rpc(database,'claim_acquisition_events',{'p_integration':config['INTEGRATION_ID'],'p_limit':1,'p_lease_seconds':120})
        if not isinstance(claims,list) or len(claims)>1:
            raise WorkerUnavailable('Invalid worker claim')
        if not claims:
            return {'status':'idle'}
        claim=claims[0]
        try:
            UUID(claim['receipt_id']); UUID(claim['lease_token']); UUID(claim['workspace_id'])
            valid=(claim['integration_id']==config['INTEGRATION_ID'] and claim['provider']=='facebook'
                   and claim['account_id']==config['PAGE_ID'] and claim['event_type']=='leadgen'
                   and isinstance(claim['external_event_id'],str) and re.fullmatch(r'[0-9]{1,200}',claim['external_event_id'])
                   and isinstance(claim['payload'],dict) and claim['payload'].get('leadgen_id')==claim['external_event_id']
                   and claim['payload'].get('page_id')==config['PAGE_ID']
                   and isinstance(claim['payload'].get('form_id'),str)
                   and re.fullmatch(r'[0-9]{1,200}',claim['payload']['form_id']))
        except (TypeError,KeyError,ValueError,AttributeError):
            valid=False
        if not valid:
            raise WorkerUnavailable('Invalid worker claim identity')
        try:
            # Separate client prevents database credentials leaking to Graph.
            async with httpx.AsyncClient(timeout=10.0,follow_redirects=False) as provider:
                data=await _retrieve(provider,config,claim['external_event_id'])
            if data.get('form_id')!=claim['payload'].get('form_id'):
                raise ProviderFailure('review','IDENTITY_CONFLICT')
            for key in ('ad_id','adset_id','campaign_id'):
                provider_id=data.get(key)
                receipt_id=claim['payload'].get(key)
                if provider_id is not None and (not isinstance(provider_id,str) or not re.fullmatch(r'[0-9]{1,200}',provider_id)):
                    raise ProviderFailure('review','INVALID_PROVIDER_DATA')
                if receipt_id is not None and (not isinstance(receipt_id,str) or not re.fullmatch(r'[0-9]{1,200}',receipt_id)):
                    raise ProviderFailure('review','INVALID_PROVIDER_DATA')
                if provider_id is not None and receipt_id is not None and provider_id!=receipt_id:
                    raise ProviderFailure('review','IDENTITY_CONFLICT')
            try:
                prepared=prepare_facebook_intake(leadgen_id=claim['external_event_id'],provider_data=data)
                if len(json.dumps(prepared).encode())>1048576:
                    raise ValueError('Prepared intake too large')
            except (ValueError,TypeError):
                raise ProviderFailure('review','INVALID_PROVIDER_DATA') from None
        except ProviderFailure as failure:
            result=await _rpc(database,'defer_acquisition_event',{'p_receipt':claim['receipt_id'],'p_lease':claim['lease_token'],
                'p_outcome':failure.outcome,'p_reason':failure.reason})
            if not isinstance(result,dict) or result.get('receipt_id')!=claim['receipt_id'] or result.get('state') not in ('retry','review'):
                raise WorkerUnavailable('Worker deferral unconfirmed')
            return {'status':result['state'],'reason_code':result.get('reason_code')}
        body={'p_receipt':claim['receipt_id'],'p_lease':claim['lease_token'],'p_prepared':prepared}
        # An uncertain completion may already have committed. Retry exactly once
        # with the identical snapshot/token; do not defer or refetch different data.
        try:
            result=await _rpc(database,'complete_facebook_acquisition_intake',body)
        except WorkerUnavailable:
            result=await _rpc(database,'complete_facebook_acquisition_intake',body)
        try:
            UUID(result['intake_id']); UUID(result['lead_id'])
            valid=(result['workspace_id']==claim['workspace_id'] and type(result['duplicate']) is bool
                   and result['classification']==prepared['classification'])
        except (KeyError,ValueError,TypeError,AttributeError):
            valid=False
        if not valid:
            raise WorkerUnavailable('Intake completion unconfirmed')
        return {'status':'completed','classification':result['classification'],'duplicate':result['duplicate']}
