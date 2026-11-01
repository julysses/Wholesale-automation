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
    admission=state_body|{'p_attempt':'ad900000-0000-4000-8000-000000000010','p_purpose':'purchase_contract'}
    # Other gateway probes may have reserved mail capacity; use expired reservations,
    # not a second quota or deletion, to exercise the shared contract RPC.
    db.query("UPDATE private.acquisition_evidence_upload_slots SET started_at=started_at-interval '121 seconds',expires_at=expires_at-interval '121 seconds'")
    admitted=rpc('admit_contract_document_upload',admission)
    if not admitted['admitted'] or admitted['contract_id']!=draft or admitted['contract_version']!=1 or admitted['execution_authorized']:
        raise AssertionError('Contract admission binding or authority failed')
    throttled=rpc('admit_contract_document_upload',admission|{'p_attempt':'ad900000-0000-4000-8000-000000000011'})
    if throttled['admitted'] or not 1<=throttled['retry_after_seconds']<=120:
        raise AssertionError('Contract actor admission cap bypassed')
    for jwt,body in [(token(other),admission),(token(),admission|{'p_version':2}),(None,admission)]:
        status,_=request('/rpc/admit_contract_document_upload',jwt,body)
        if status not in (401,403):raise AssertionError('Contract admission target/session bypass accepted')
    status,rows=request('/acquisition_evidence_artifacts?select=id&contract_id=eq.'+draft,token(other))
    if status!=200 or rows!=[]:raise AssertionError('Contract evidence RLS leaked')
    from datetime import datetime, timedelta, timezone
    from uuid import UUID
    from tools.acquisition_contract_attestation import ContractVerificationSigningKey, build_contract_scan_attestation
    signing_key='ae900000-0000-4000-8000-000000000001'
    observation_id='ae900000-0000-4000-8000-000000000002'
    scanner_version='ClamAV 1.4.3/12345/Thu Oct 29 00:00:00 2026'
    db.query("INSERT INTO private.acquisition_evidence_verification_keys(id,workspace_id,secret,scanner_version,scan_policy_version,valid_from,valid_until,reviewed_by,approval_ref) VALUES(%s,%s,decode(repeat('ab',32),'hex'),%s,'synthetic-v1',clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 hour',%s,%s)",[signing_key,workspace,scanner_version,admin,observation_id])
    state=rpc('contract_document_state',state_body)
    now=datetime.now(timezone.utc)
    key=ContractVerificationSigningKey(UUID(signing_key),UUID(workspace),bytes.fromhex('ab'*32),frozenset({'purchase_contract'}),scanner_version,'synthetic-v1',now-timedelta(hours=1),now+timedelta(hours=1))
    observed={k:state[k] for k in ('workspace_id','contract_id','contract_version','artifact_id','purpose','media_type','retain_until','retention_policy_id','checked_at')}
    observed.update(status='scan_observed',sha256=state['expected_sha256'],byte_size=state['expected_byte_size'],scan_checked_at=state['checked_at'],registry_checked_at=state['checked_at'],
        scanner='clamav-instream-v1',scanner_version=scanner_version,scan_policy_version='synthetic-v1',scan_status='no_detection',
        verifier_version='acquisition-contract-document-bytes-v1',registry_verifier_version='acquisition-contract-document-registry-v1',
        verification_persisted=False,scan_persisted=False,preview_authorized=False,legal_review_approved=False,execution_authorized=False)
    signed=build_contract_scan_attestation(observed,request_id=UUID(observation_id),actor_id=UUID(admin),session_id=UUID(admin),key=key,clock=lambda:now)
    status,_=request('/rpc/record_contract_document_verification',token(),signed)
    if status!=403:raise AssertionError('Unreviewed contract key scope was accepted')
    db.query("INSERT INTO private.acquisition_contract_verification_key_scopes(workspace_id,key_id,purpose,reviewed_by,approval_ref,valid_from,valid_until) VALUES(%s,%s,'purchase_contract',%s,%s,clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 hour')",[workspace,signing_key,admin,observation_id])
    # Register native-version documents before terms advance the canonical version.
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
    linked_observation_id='ae900000-0000-4000-8000-000000000003'
    linked_state=rpc('contract_document_state',state_body|{'p_artifact':api_document})
    linked_observed=observed|{name:linked_state[name] for name in ('artifact_id','checked_at','retain_until')}
    linked_observed.update(scan_checked_at=linked_state['checked_at'],registry_checked_at=linked_state['checked_at'])
    linked_signed=build_contract_scan_attestation(linked_observed,request_id=UUID(linked_observation_id),actor_id=UUID(admin),session_id=UUID(admin),key=key)
    rpc('record_contract_document_verification',linked_signed)
    import asyncio
    import tempfile
    from pathlib import Path
    from tools.acquisition_evidence_journal import EvidenceJournal
    from tools.acquisition_evidence_persistence import EvidencePersistenceUnconfirmed
    scan_commits=[]; scan_requests=[]
    class RawScanReply(httpx.AsyncByteStream):
        def __init__(self, data): self.data=json.dumps(data).encode()
        async def __aiter__(self): yield self.data
    def scan_gateway(req):
        if str(req.url) not in ('https://contract-gateway.test/rest/v1/rpc/record_contract_document_verification',
                               'https://contract-gateway.test/rest/v1/rpc/contract_document_scan_state'):
            raise AssertionError('Unexpected contract observation destination')
        writing=req.url.path.endswith('/record_contract_document_verification')
        if writing: scan_requests.append(req.content)
        status,data=request(req.url.path.removeprefix('/rest/v1'),
            req.headers['authorization'].removeprefix('Bearer '),json.loads(req.content))
        if status==200 and writing:
            scan_commits.append(data)
            if len(scan_commits)==1: raise httpx.ReadTimeout('Synthetic lost reply after actual commit')
        return httpx.Response(status,stream=RawScanReply(data),headers={'content-type':'application/json'})
    async def reconcile_contract_scan(directory):
        journal=EvidenceJournal(directory); journal.prepare(signed)
        scope=dict(workspace_id=UUID(workspace),contract_id=UUID(draft),contract_version=1,
            purpose='purchase_contract',artifact_id=UUID(signed['p_artifact']),actor_id=UUID(admin),session_id=UUID(admin))
        async with httpx.AsyncClient(base_url='https://contract-gateway.test/rest/v1/',trust_env=False,
                transport=httpx.MockTransport(scan_gateway),headers={'Authorization':'Bearer '+token(),'apikey':'synthetic'}) as client:
            store=AcquisitionStore(client)
            try: await store.persist_journaled_contract_observation(journal,UUID(observation_id),**scope)
            except EvidencePersistenceUnconfirmed: pass
            else: raise AssertionError('Lost committed scan reply reported confirmed')
            reopened=EvidenceJournal(directory)
            if reopened.load(UUID(observation_id)) != (signed,'unconfirmed'):
                raise AssertionError('Exact signed contract request was not retained')
            receipt=await store.persist_journaled_contract_observation(reopened,UUID(observation_id),**scope)
            if reopened.load(UUID(observation_id))[1]!='confirmed': raise AssertionError('Contract recovery not journaled')
            read_scope={k:v for k,v in scope.items() if k not in ('actor_id','session_id','artifact_id')}
            current=await store.contract_document_scan_state(scope['artifact_id'],**read_scope)
            if current.status!='no_detection_observed' or current.observation_id!=UUID(observation_id) or current.legal_review_approved:
                raise AssertionError('Contract current scan state binding failed')
            review_policy='af900000-0000-4000-8000-000000000001'
            review_id='af900000-0000-4000-8000-000000000002'
            withdrawal_id='af900000-0000-4000-8000-000000000003'
            db.query("INSERT INTO private.acquisition_contract_review_policies(id,workspace_id,kind,purpose,reviewer_id,max_review_seconds,valid_from,valid_until,reviewed_by,approval_ref) VALUES(%s,%s,'contract_review','purchase_contract',%s,1800,clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 hour',%s,%s)",[review_policy,workspace,admin,admin,review_id])
            review_body=dict(p_id=review_id,p_workspace=workspace,p_contract=draft,p_version=1,p_kind='contract_review',p_expected_sequence=0,
                p_status='approved',p_artifact=signed['p_artifact'],p_verification=observation_id,p_policy=review_policy,
                p_expires=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),p_personally_reviewed=True,
                p_note='Synthetic authorized human review of exact contract document contents.')
            candidate_scope=dict(p_workspace=workspace,p_contract=draft,p_version=1,p_kind='contract_review',p_artifact=signed['p_artifact'])
            choice=rpc('contract_review_candidate',candidate_scope)
            if choice['status']!='ready_for_human_review' or choice['candidate']['verification_id']!=observation_id or choice['candidate']['policy_id']!=review_policy or choice['execution_authorized']:
                raise AssertionError('Actual review candidate did not bind exact policy/evidence')
            for jwt in (token(other),None,token(role='service_role')):
                status,_=request('/rpc/contract_review_candidate',jwt,candidate_scope)
                if status not in (401,403):raise AssertionError('Review candidate gateway scope bypass')
            human_review=rpc('record_contract_review',review_body)
            replay=rpc('record_contract_review',review_body)
            review_scope=dict(p_workspace=workspace,p_contract=draft,p_version=1,p_kind='contract_review')
            current_review=rpc('contract_review_state',review_scope)
            if human_review['duplicate'] or not replay['duplicate'] or replay['approval_current'] or replay['execution_authorized'] or not current_review['approval_current']:
                raise AssertionError('Contract human review persistence/current distinction failed')
            review_path=f'/api/acquisition/workspaces/{workspace}/contracts/{draft}/versions/1/reviews/contract_review'
            review_request={'id':review_id,'expected_sequence':0,'status':'approved','artifact_id':signed['p_artifact'],
                'verification_id':observation_id,'policy_id':review_policy,'expires_at':review_body['p_expires'],
                'personally_reviewed':True,'note':review_body['p_note']}
            document_drops['rpc/record_contract_review']=True
            with TestClient(app) as review_client:
                lost=review_client.post(review_path,json=review_request,headers=headers)
                recovered=review_client.post(review_path,json=review_request,headers=headers)
                if lost.status_code!=503 or recovered.status_code!=200 or not recovered.json()['duplicate'] or recovered.json()['approval_current']:
                    raise AssertionError('Mounted human review exact response-loss recovery failed')
                candidate_path=review_path+'/documents/'+signed['p_artifact']+'/candidate'
                candidate_api=review_client.get(candidate_path,headers=headers)
                if candidate_api.status_code!=200 or candidate_api.headers.get('cache-control')!='no-store' or candidate_api.json()['candidate']['expected_sequence']!=1:
                    raise AssertionError('Mounted exact review candidate unavailable')
                for identity in ({'Authorization':'Bearer '+token(other)},{}):
                    if review_client.get(candidate_path,headers=identity).status_code not in (401,403):
                        raise AssertionError('Mounted candidate scope bypass')
                if review_client.get(candidate_path.replace('/versions/1/','/versions/2/'),headers=headers).status_code!=403:
                    raise AssertionError('Mounted candidate version bypass')
                current_api=review_client.get(review_path,headers=headers)
                if current_api.status_code!=200 or not current_api.json()['approval_current'] or current_api.headers.get('cache-control')!='no-store':
                    raise AssertionError('Mounted current human review unavailable')
                for identity in ({'Authorization':'Bearer '+token(other)},{}):
                    if review_client.get(review_path,headers=identity).status_code not in (401,403):
                        raise AssertionError('Mounted human review read scope bypass')
                    if review_client.post(review_path,json=review_request,headers=identity).status_code not in (401,403):
                        raise AssertionError('Mounted human review write scope bypass')
                if review_client.get(review_path.replace('/versions/1/','/versions/2/'),headers=headers).status_code!=403:
                    raise AssertionError('Mounted human review version bypass')
            for jwt,wrong in [(token(other),review_body),(None,review_body),(token(),review_body|{'p_version':2})]:
                status,_=request('/rpc/record_contract_review',jwt,wrong)
                if status not in (401,403):raise AssertionError('Contract human review scope bypass')
            from acquisition_contract_terms_http import verify_terms_http, verify_terms_revocation_http
            terms_path,terms_body=verify_terms_http(db,app,document_drops,token,workspace,draft,signed['p_artifact'],observed['sha256'],other,lead)
            reference_args=dict(p_workspace=workspace,p_contract=draft,p_version=2,p_artifact=signed['p_artifact'])
            reference=rpc('contract_reference_state',reference_args)
            if reference['reference_type']!='term_source' or reference['source_version']!=1 or reference['status']!='available_for_review' or reference['review_approved'] or reference['execution_authorized']:
                raise AssertionError('Original term source was relabeled or treated as approval')
            for identity in (token(other),None,token(role='service_role')):
                status,_=request('/rpc/contract_reference_state',identity,reference_args)
                if status not in (401,403):raise AssertionError('Contract source reference gateway scope bypass')

            from acquisition_source_review_http import verify_source_review_http,verify_source_review_revocation_http
            source_review_path,source_review_body=verify_source_review_http(db,app,document_drops,headers,workspace,draft,review_request,{'Authorization':'Bearer '+token(other)})
            from acquisition_contract_links_http import verify_links_http,verify_link_withdrawal_http
            link_path,link_body=verify_links_http(db,app,document_drops,headers,{'Authorization':'Bearer '+token(other)},workspace,draft,api_document,linked_observation_id,observed['sha256'])
            from acquisition_signature_review_http import verify_signature_http,verify_signature_revocation_http
            signature_path,signature_body=verify_signature_http(db,app,document_drops,headers,{'Authorization':'Bearer '+token(other)},workspace,draft,terms_body,source_review_body)
            from acquisition_contract_transition_http import verify_transition_http
            verify_transition_http(db,app,document_drops,headers,{'Authorization':'Bearer '+token(other)},workspace,draft)
            from acquisition_pending_document_http import verify_pending_document_http
            verify_pending_document_http(db,app,document_drops,headers,{'Authorization':'Bearer '+token(other)},workspace,draft,policy,rpc)
            from acquisition_execution_review_http import verify_execution_http,verify_execution_revocation_http
            execution_path,execution_body=verify_execution_http(db,app,document_drops,headers,{'Authorization':'Bearer '+token(other)},workspace,draft,source_review_body)
            from acquisition_contract_transition_http import verify_executed_transition_http
            verify_executed_transition_http(db,app,document_drops,headers,{'Authorization':'Bearer '+token(other)},workspace,draft)
            from acquisition_deadline_review_http import verify_deadline_http
            verify_deadline_http(db,app,document_drops,headers,{'Authorization':'Bearer '+token(other)},workspace,admin,rpc,policy,key,observed,review_policy)
            db.query('UPDATE private.acquisition_contract_verification_key_scopes SET revoked_at=clock_timestamp() WHERE workspace_id=%s AND key_id=%s',[workspace,signing_key])
            verify_execution_revocation_http(db,app,document_drops,headers,execution_path,execution_body)
            verify_source_review_revocation_http(db,app,document_drops,headers,source_review_path,source_review_body)
            verify_terms_revocation_http(app,token,terms_path,terms_body)
            verify_link_withdrawal_http(db,app,document_drops,headers,{'Authorization':'Bearer '+token(other)},link_path,link_body)
            verify_signature_revocation_http(db,app,document_drops,headers,signature_path,signature_body)
            reference=rpc('contract_reference_state',reference_args)
            if reference['status']!='requires_review' or reference['verification_id'] is not None:
                raise AssertionError('Original source reference retained revoked verification authority')

            stale=await store.contract_document_scan_state(scope['artifact_id'],**read_scope)
            if stale.status!='requires_review' or stale.observation_id is not None or stale.execution_authorized:
                raise AssertionError('Revoked contract scope retained current scan authority')
            if rpc('contract_review_state',review_scope)['approval_current']:
                raise AssertionError('Human review survived revoked scan authority')
            with TestClient(app) as review_client:
                candidate_hold=review_client.get(candidate_path,headers=headers)
                if candidate_hold.status_code!=200 or candidate_hold.json()['candidate'] is not None or candidate_hold.json()['withdrawal']['expected_sequence']!=1:
                    raise AssertionError('Mounted candidate lost revoked evidence/withdrawal boundary')
                held=review_client.get(review_path,headers=headers)
                if held.status_code!=200 or held.json()['approval_current'] or held.json()['status']!='requires_review':
                    raise AssertionError('Mounted review retained revoked scan authority')
            held_choice=rpc('contract_review_candidate',candidate_scope)
            if held_choice['candidate'] is not None or held_choice['withdrawal']['expected_sequence']!=1:
                raise AssertionError('Candidate did not retain withdrawal and remove revoked evidence')
            withdrawal=review_body|dict(p_id=withdrawal_id,p_expected_sequence=1,p_status='withdrawn',p_expires=None,p_personally_reviewed=False)
            if rpc('record_contract_review',withdrawal)['status']!='withdrawn' or not rpc('record_contract_review',withdrawal)['duplicate']:
                raise AssertionError('Human review withdrawal exact recovery failed')
            if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_review' AND entity_id=%s",[review_id])!=[{'n':1}]:
                raise AssertionError('Human review retry duplicated immutable audit')
            return receipt
    with tempfile.TemporaryDirectory(prefix='contract-observation-recovery-') as directory:
        recovered_scan=asyncio.run(reconcile_contract_scan(Path(directory)))
    first_scan=scan_commits[0]
    if len(scan_requests)!=2 or scan_requests[0]!=scan_requests[1]:
        raise AssertionError('Contract observation retry changed signed request')
    if first_scan['duplicate'] or not recovered_scan['duplicate'] or recovered_scan['contract_id']!=draft or recovered_scan['contract_version']!=1:
        raise AssertionError('Contract observation exact recovery or target failed')
    if any(recovered_scan[k] for k in ('preview_authorized','legal_review_approved','execution_authorized')):
        raise AssertionError('Persisted scan implied approval')
    # Signature preparation now creates version3; version4 remains nonexistent.
    for jwt,body in [(token(other),signed),(token(),signed|{'p_version':4}),(None,signed)]:
        status,_=request('/rpc/record_contract_document_verification',jwt,body)
        if status not in (401,403):raise AssertionError('Contract observation scope/session bypass accepted')
    status,rows=request('/acquisition_evidence_verifications?select=id&contract_id=eq.'+draft,token(other))
    if status!=200 or rows!=[]:raise AssertionError('Contract observation RLS leaked')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_evidence_verification' AND entity_id=%s",[observation_id])!=[{'n':1}]:
        raise AssertionError('Contract observation retry duplicated audit')
    revoke=state_body|{'p_id':revocation,'p_reason':'Synthetic document withdrawn from current review.'}
    if rpc('revoke_contract_document',revoke)['duplicate'] or not rpc('revoke_contract_document',revoke)['duplicate']:
        raise AssertionError('Contract document revocation recovery failed')
    if rpc('contract_document_state',state_body)['status']!='revoked':
        raise AssertionError('Contract document revocation missing from state')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_document' AND entity_id=%s",[document])!=[{'n':2}]:
        raise AssertionError('Contract document retry duplicated audit')
    with TestClient(app) as client:
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
        scan_path=api_path+'/'+document+'/scan-state?purpose=purchase_contract'
        scan_response=client.get(scan_path,headers=headers)
        if scan_response.status_code!=200 or scan_response.headers.get('cache-control')!='no-store' or scan_response.json()['status']!='revoked' or scan_response.json()['legal_review_approved']:
            raise AssertionError('Contract scan API lost retained non-approving state')
        for identity in ({'Authorization':'Bearer '+token(other)},{}):
            if client.get(scan_path,headers=identity).status_code not in (401,403):
                raise AssertionError('Contract scan API tenant/session bypass')
        for wrong_path in (scan_path.replace('/versions/1/','/versions/2/'),scan_path.replace('purpose=purchase_contract','purpose=title_report')):
            if client.get(wrong_path,headers=headers).status_code!=403:
                raise AssertionError('Contract scan API target/purpose bypass')
        listing=client.get(api_path+'?purpose=purchase_contract&limit=1',headers=headers)
        if listing.status_code!=200:raise AssertionError('Document discovery API unavailable')
        page=listing.json()
        if page['current_policy']['id']!=policy or page['items'][0]['artifact_id']!=document or page['next_after']!=document or page['upload_enabled']:
            raise AssertionError('Document discovery policy/page/gate binding failed')
        next_page=client.get(api_path+'?purpose=purchase_contract&limit=1&after='+document,headers=headers)
        if next_page.status_code!=200 or next_page.json()['items'][0]['artifact_id']!=api_document or next_page.json()['next_after'] is not None:
            raise AssertionError('Document discovery cursor continuity failed')
        if page['items'][0]['status']!='revoked' or next_page.json()['items'][0]['status']!='revoked':
            raise AssertionError('Document discovery erased retained revocation history')
        for identity in ({'Authorization':'Bearer '+token(other)},{}):
            if client.get(api_path+'?purpose=purchase_contract',headers=identity).status_code not in (401,403):
                raise AssertionError('Document discovery tenant/session bypass')
        if client.get(api_path.replace('/versions/1/','/versions/4/')+'?purpose=purchase_contract',headers=headers).status_code!=403:
            raise AssertionError('Document discovery wrong-version bypass')
        if client.post(api_path+'/'+api_document+'/bytes',headers=headers,content=b'not accepted').status_code not in (404,405):
            raise AssertionError('Contract document upload unexpectedly enabled')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_document' AND entity_id=%s",[api_document])!=[{'n':2}]:
        raise AssertionError('Document API recovery duplicated immutable audits')
    return ['contract API actual commit loss and exact recovery','contract API canonical draft and immutable audit',
            'contract API real tenant and anonymous isolation','contract API expired session denied','contract seller actual canonical join and property isolation',
            'contract document real registration exact retry','contract document target session and tenant isolation',
            'contract document revocation exact retry','contract document immutable audit convergence',
            'contract document API committed registration recovery','contract document API committed revocation recovery',
            'contract document API fresh state and scope isolation','contract document API immutable audit and upload hold',
            'contract upload admission binding and shared actor cap','contract upload admission scope and session isolation',
            'contract document discovery real policy pagination and retained state','contract document discovery API tenant and version isolation',
            'contract observation real signature and separately reviewed key scope','contract observation exact retry and immutable audit',
            'contract observation real tenant session and version isolation',
            'contract observation typed journal recovery after actual commit loss',
            'contract scan current typed gateway state and exact observation',
            'contract scan purpose scope revocation removes current observation',
            'contract scan mounted API retained state and tenant version purpose isolation',
            'contract human review exact gateway retry and immutable audit',
            'contract human review gateway tenant session and version isolation',
            'contract human review current scan revocation and withdrawal recovery',
            'mounted human review exact retry after response loss',
            'mounted human review scope isolation and fresh revoked state',
            'review candidate real gateway exact authority and withdrawal after revocation',
            'mounted review candidate exact scope expiry and revoked evidence hold',
            'terms API sourced save actual commit loss and exact retry',
            'terms API immutable paged history and updated draft list',
            'terms API workspace isolation and expected version conflicts',
            'terms API no approval carryover and revocation blocks new versions',
            'contract source reference original version and gateway role isolation',
            'contract source reference current scan revocation hold',
            'source-aware human review mounted candidate and exact commit-loss recovery',
            'source-aware human review original evidence FK and target workspace isolation',
            'source-aware human review revocation and withdrawal recovery',
            'mounted source reference discovery and exact original detail',
            'mounted source reference workspace isolation and native pagination',
            'mounted source reference revocation removes current verification',
            'document link API actual commit loss and exact original source recovery',
            'document link API workspace session target and conflict isolation',
            'document link withdrawal after revoked source while paused preserves original audit',
            'signature review API committed reply loss exact retry and independent basis',
            'signature review API tenant session target and request conflict denial',
            'signature review API revoked source and paused withdrawal recovery without legal transition',
            'signature candidate API exact original document basis and scoped reviewer policy',
            'signature candidate API paused hold preserves independent original withdrawal',
            'lifecycle API committed response loss and exact historical retry',
            'lifecycle API tenant session and conflicting reason rejection',
            'lifecycle version preservation and continued guided contract visibility',
            'lifecycle candidate current exact handoff and workspace isolation',
            'lifecycle candidate recorded state removes duplicate action',
            'pending contract document registration exact commit-loss recovery and isolation',
            'pending contract document admission preserves terms status and unverified history',
            'execution review API actual commit loss and exact findings recovery',
            'execution review API tenant session conflict and immutable lifecycle boundaries',
            'execution review current source revocation and paused withdrawal recovery',
            'execution candidate exact returned source and scoped reviewer policy',
            'execution candidate paused hold preserves original withdrawal',
            'executed transition actual commit loss and exact historical recovery',
            'executed transition tenant conflict checks and unchanged terms with visible history',
            'deadline API actual approval commit loss and exact historical recovery',
            'deadline API original withdrawal recovery after policy revocation',
            'deadline API workspace conflicts and unchanged calendar terms status and audit',
            'deadline state exact term identity shared sequence and independent unreviewed term',
            'deadline state policy revocation and original withdrawal history',
            'deadline choices exact original source selected policy and scoped access',
            'deadline choices retain original withdrawal under policy hold and remove it after withdrawal']
