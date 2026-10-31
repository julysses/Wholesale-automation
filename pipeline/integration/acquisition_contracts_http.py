"""Draft API through actual local PostgREST; all records and JWTs synthetic.

The test injects only the socket transport into the existing user-scoped store.
Database writes, RLS, receipts and returned JSON are real. Hosted Auth is not tested.
"""
import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
import httpx


def verify_contracts_http(db, request, token, admin, other, workspace):
    from tools.acquisition_store import AcquisitionStore, acquisition_store
    from web.api.acquisition_api import router

    lead='ac900000-0000-4000-8000-000000000001'
    prop='ac900000-0000-4000-8000-000000000002'
    owner='ac900000-0000-4000-8000-000000000003'
    relation='ac900000-0000-4000-8000-000000000004'
    analysis='ac900000-0000-4000-8000-000000000005'
    offer='ac900000-0000-4000-8000-000000000006'
    approval='ac900000-0000-4000-8000-000000000007'
    draft='ac900000-0000-4000-8000-000000000008'
    db.query("INSERT INTO public.leads(id,property_address,city,owner_first_name,owner_last_name) VALUES(%s,'901 Draft Fixture','Dallas','Synthetic','Seller')",[lead])
    db.query("INSERT INTO wholesale_ingest.properties(id,state,county,parcel_id,lead_id) VALUES(%s,'TX','Dallas','synthetic-contract-http',%s)",[prop,lead])

    def rpc(name,body,*,service=False):
        status,data=request('/rpc/'+name,token(role='service_role') if service else token(),body)
        if status!=200:raise AssertionError(f'Contract HTTP fixture {name} failed: {status} {data}')
        return data

    scope={'p_workspace':workspace}
    rpc('bind_acquisition_lead',scope|{'p_lead':lead,'p_property':prop})
    rpc('create_acquisition_owner',scope|{'p_id':owner,'p_lead':lead})
    rpc('associate_acquisition_owner',scope|{'p_id':relation,'p_owner':owner,'p_lead':lead,
        'p_relationship':'reported_owner','p_note':'Synthetic reported ownership, not verified title'})
    rpc('reserve_acquisition_analysis',scope|{'p_id':analysis,'p_lead':lead,
        'p_inputs':{'cases':{case:{'strategy':'fix_and_flip'} for case in ('base','downside','upside')}}})
    snapshot=rpc('read_acquisition_calculation',scope|{'p_id':analysis},service=True)
    outputs={'status':'calculated','calculation_version':'acquisition-underwriting-v1','strategy':'fix_and_flip',
        'cases':{case:{'status':'calculated','mao':'150000.00','proposed_offer_range':{'low':'120000.00','high':'150000.00'}} for case in ('base','downside','upside')},
        'binding_offer':False,'human_approval_required':True}
    rpc('complete_acquisition_calculation',scope|{'p_id':analysis,'p_input_hash':snapshot['input_hash'],'p_outputs':outputs},service=True)
    rpc('propose_acquisition_offer',scope|{'p_id':offer,'p_analysis':analysis,'p_case':'base','p_amount':140000,'p_note':'Synthetic amount only'})
    rpc('review_acquisition_offer',scope|{'p_id':approval,'p_offer':offer,'p_expected_sequence':1,
        'p_status':'amount_approved','p_note':'Synthetic internal review',
        'p_review_notes':{key:'Synthetic unresolved review, not verified facts' for key in ('title','liens','occupancy','valuation','repairs','financing','downside')}})

    drop_reply=[True];commits=[]
    document_drops={'rpc/register_contract_document':True,'rpc/revoke_contract_document':True}
    class Store(AcquisitionStore):
        async def request(self,method,path,**kwargs):
            result=await super().request(method,path,**kwargs)
            if path=='rpc/create_acquisition_contract_draft':
                commits.append(result)
                if drop_reply[0]:
                    drop_reply[0]=False
                    raise HTTPException(503,'Synthetic response lost after commit')
            if document_drops.get(path):
                document_drops[path]=False
                raise HTTPException(503,'Synthetic document response lost after commit')
            return result

    def gateway(req):
        if req.url.host!='localhost' or req.method not in ('GET','POST'):
            raise AssertionError('Unexpected gateway destination or method')
        path=req.url.path+('?' + req.url.query.decode() if req.url.query else '')
        jwt=req.headers.get('authorization','').removeprefix('Bearer ') or None
        status,data=request(path,jwt,json.loads(req.content) if req.method=='POST' else None)
        return httpx.Response(status,json=data)

    async def store(incoming:Request):
        async with httpx.AsyncClient(base_url='http://localhost/',trust_env=False,
                transport=httpx.MockTransport(gateway),headers={'Authorization':incoming.headers.get('authorization','')}) as client:
            yield Store(client)

    app=FastAPI();app.include_router(router);app.dependency_overrides[acquisition_store]=store
    path=f'/api/acquisition/workspaces/{workspace}/contracts/drafts'
    body={'id':draft,'offer_id':offer,'offer_sequence':2,'owner_relationship_id':relation,'name':'Synthetic contract HTTP draft'}
    headers={'Authorization':'Bearer '+token()}
    with TestClient(app) as client:
        sellers=client.get(path+'/sellers',params={'lead_id':lead,'property_id':prop},headers=headers)
        if sellers.status_code!=200 or len(sellers.json()['items'])!=1:
            raise AssertionError('Actual seller relationship join failed')
        choice=sellers.json()['items'][0]
        if choice['id']!=relation or choice['owner_id']!=owner or choice['seller']['display_name']!='Synthetic Seller':
            raise AssertionError('Seller choice lost canonical identity/name')
        if choice['verification_status']!='unverified' or sellers.json()['ownership_verified'] or sellers.json()['execution_authorized']:
            raise AssertionError('Seller choices implied verified title or execution')
        foreign_sellers=client.get(path+'/sellers',params={'lead_id':lead,'property_id':prop},headers={'Authorization':'Bearer '+token(other)})
        wrong_property=client.get(path+'/sellers',params={'lead_id':lead,'property_id':draft},headers=headers)
        if foreign_sellers.json().get('items')!=[] or wrong_property.json().get('items')!=[]:
            raise AssertionError('Seller choices leaked across workspace/property')
        lost=client.post(path,json=body,headers=headers)
        if lost.status_code!=503 or len(commits)!=1 or commits[0]['duplicate']:
            raise AssertionError('Draft response loss did not follow real commit')
        retry=client.post(path,json=body,headers=headers)
        if retry.status_code!=200 or retry.json()!={'deal_id':draft,'version':1,'status':'draft','duplicate':True,'execution_authorized':False}:
            raise AssertionError('Draft exact recovery failed')
        changed=client.post(path,json=body|{'name':'Changed request'},headers=headers)
        if changed.status_code!=409:raise AssertionError('Conflicting draft retry accepted')
        listed=client.get(path,params={'lead_id':lead},headers=headers)
        if listed.status_code!=200 or len(listed.json()['items'])!=1 or listed.json()['items'][0]['id']!=draft:
            raise AssertionError('Draft API canonical record missing')
        if listed.headers.get('cache-control')!='no-store':raise AssertionError('Draft page cacheable')
        foreign={'Authorization':'Bearer '+token(other)}
        if client.get(path,params={'lead_id':lead},headers=foreign).json().get('items')!=[]:
            raise AssertionError('Draft leaked across workspaces')
        if client.post(path,json=body,headers=foreign).status_code!=403:
            raise AssertionError('Foreign draft retry accepted')
        if client.post(path,json=body).status_code not in (401,403):
            raise AssertionError('Anonymous draft accepted')
        if db.query('SELECT count(*) AS n FROM public.acquisition_contract_versions WHERE deal_id=%s',[draft])!=[{'n':1}]:
            raise AssertionError('Draft recovery duplicated versions')
        if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract' AND entity_id=%s",[draft])!=[{'n':1}]:
            raise AssertionError('Draft recovery duplicated audit')
        db.query('UPDATE auth.sessions SET not_after=clock_timestamp()-interval \'1 second\' WHERE id=%s',[admin])
        try:
            if client.post(path,json=body,headers=headers).status_code!=403:
                raise AssertionError('Expired session recovered a draft')
        finally:db.query('UPDATE auth.sessions SET not_after=NULL WHERE id=%s',[admin])
    document='ad900000-0000-4000-8000-000000000001'
    policy='ad900000-0000-4000-8000-000000000002'
    revocation='ad900000-0000-4000-8000-000000000003'
    db.query("INSERT INTO private.acquisition_evidence_policies(id,workspace_id,purpose,version,retention_seconds,valid_from,valid_until,approval_ref,reviewed_by,reviewed_at) VALUES(%s,%s,'purchase_contract',1,86400,'2026-01-01','2099-01-01',%s,%s,'2026-01-01')",[policy,workspace,revocation,admin])
    registration=scope|{'p_id':document,'p_contract':draft,'p_version':1,'p_purpose':'purchase_contract',
        'p_sha256':'b'*64,'p_byte_size':123,'p_media_type':'application/pdf','p_policy':policy,
        'p_note':'Synthetic contract document source; no actual signature.'}
    first=rpc('register_contract_document',registration)
    recovered=rpc('register_contract_document',registration)
    if first['duplicate'] or not recovered['duplicate'] or first['execution_authorized'] or first['bytes_verified']:
        raise AssertionError('Contract document retry or authority boundary failed')
    if first['artifact_id']!=document or first['contract_id']!=draft or first['contract_version']!=1:
        raise AssertionError('Contract document target binding lost')
    for jwt,body in [(token(other),registration),(token(),registration|{'p_version':2}),(None,registration)]:
        status,_=request('/rpc/register_contract_document',jwt,body)
        if status not in (401,403):raise AssertionError('Contract document target/session bypass accepted')
    state_body=scope|{'p_contract':draft,'p_version':1,'p_artifact':document}
    if rpc('contract_document_state',state_body)['status']!='pending_verification':
        raise AssertionError('Contract document metadata implies verification')
    status,rows=request('/acquisition_evidence_artifacts?select=id&contract_id=eq.'+draft,token(other))
    if status!=200 or rows!=[]:raise AssertionError('Contract evidence RLS leaked')
    revoke=state_body|{'p_id':revocation,'p_reason':'Synthetic document withdrawn from current review.'}
    if rpc('revoke_contract_document',revoke)['duplicate'] or not rpc('revoke_contract_document',revoke)['duplicate']:
        raise AssertionError('Contract document revocation recovery failed')
    if rpc('contract_document_state',state_body)['status']!='revoked':
        raise AssertionError('Contract document revocation missing from state')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_document' AND entity_id=%s",[document])!=[{'n':2}]:
        raise AssertionError('Contract document retry duplicated audit')
    api_document='ad900000-0000-4000-8000-000000000004'
    api_revocation='ad900000-0000-4000-8000-000000000005'
    api_path=f'/api/acquisition/workspaces/{workspace}/contracts/{draft}/versions/1/documents'
    api_body={'id':api_document,'purpose':'purchase_contract','expected_sha256':'b'*64,'expected_byte_size':123,
        'media_type':'application/pdf','retention_policy_id':policy,'provenance_note':'Synthetic document metadata API provenance.'}
    with TestClient(app) as client:
        if client.post(api_path,json=api_body,headers=headers).status_code!=503:
            raise AssertionError('Document registration commit loss was not preserved')
        retry=client.post(api_path,json=api_body,headers=headers)
        if retry.status_code!=200 or not retry.json()['duplicate'] or retry.json()['execution_authorized']:
            raise AssertionError('Document API exact registration recovery failed')
        if client.post(api_path,json=api_body|{'expected_byte_size':124},headers=headers).status_code!=409:
            raise AssertionError('Document API conflicting request accepted')
        state=client.get(api_path+'/'+api_document,headers=headers)
        if state.status_code!=200 or state.json()['status']!='pending_verification' or state.json()['legal_review_approved']:
            raise AssertionError('Document API state or approval boundary failed')
        if state.headers.get('cache-control')!='no-store':raise AssertionError('Document API state cacheable')
        for identity in ({'Authorization':'Bearer '+token(other)},{}):
            if client.get(api_path+'/'+api_document,headers=identity).status_code not in (401,403):
                raise AssertionError('Document API tenant/anonymous read accepted')
        if client.get(api_path.replace('/versions/1/','/versions/2/')+'/'+api_document,headers=headers).status_code!=403:
            raise AssertionError('Document API wrong version accepted')
        revoke_body={'id':api_revocation,'reason':'Synthetic document withdrawn through actual API.'}
        revoke_path=api_path+'/'+api_document+'/revocations'
        if client.post(revoke_path,json=revoke_body,headers=headers).status_code!=503:
            raise AssertionError('Document revocation commit loss was not preserved')
        recovered=client.post(revoke_path,json=revoke_body,headers=headers)
        if recovered.status_code!=200 or not recovered.json()['duplicate']:
            raise AssertionError('Document API revocation recovery failed')
        if client.get(api_path+'/'+api_document,headers=headers).json()['status']!='revoked':
            raise AssertionError('Document API lost revoked state')
        if client.post(api_path+'/'+api_document+'/bytes',headers=headers,content=b'not accepted').status_code not in (404,405):
            raise AssertionError('Contract document upload unexpectedly enabled')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_document' AND entity_id=%s",[api_document])!=[{'n':2}]:
        raise AssertionError('Document API recovery duplicated immutable audits')
    return ['contract API actual commit loss and exact recovery','contract API canonical draft and immutable audit',
            'contract API real tenant and anonymous isolation','contract API expired session denied','contract seller actual canonical join and property isolation',
            'contract document real registration exact retry','contract document target session and tenant isolation',
            'contract document revocation exact retry','contract document immutable audit convergence',
            'contract document API committed registration recovery','contract document API committed revocation recovery',
            'contract document API fresh state and scope isolation','contract document API immutable audit and upload hold']
