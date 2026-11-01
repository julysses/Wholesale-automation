"""Existing mounted review API over source-version-aware database decisions."""
from fastapi.testclient import TestClient


def verify_source_review_http(db,app,drops,headers,workspace,contract,original_request,foreign_headers):
    path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/2/reviews/contract_review'
    body=original_request|{'id':'af920000-0000-4000-8000-000000000001',
        'note':'Synthetic fresh review of changed version two and its original source clauses.'}
    candidate=path+'/documents/'+body['artifact_id']+'/candidate'
    references=path.rsplit('/reviews/',1)[0]+'/references'
    with TestClient(app) as client:
        listed=client.get(references+'?purpose=purchase_contract&limit=1',headers=headers)
        if listed.status_code!=200 or listed.headers.get('cache-control')!='no-store' or len(listed.json()['items'])!=1:
            raise AssertionError('Mounted source reference discovery unavailable')
        source=listed.json()['items'][0]
        if source['artifact_id']!=body['artifact_id'] or source['source_version']!=1 or source['contract_version']!=2 or source['reference_type']!='term_source' or source['review_approved']:
            raise AssertionError('Mounted original-source reference identity lost')
        detail=client.get(references+'/'+body['artifact_id'],headers=headers)
        if detail.status_code!=200 or detail.json()['verification_id']!=body['verification_id']:
            raise AssertionError('Mounted original-source detail unavailable')
        for identity in (foreign_headers,{}):
            if client.get(references+'?purpose=purchase_contract',headers=identity).status_code not in (401,403):
                raise AssertionError('Reference discovery crossed workspace/session')
        native=client.get(references.replace('/versions/2/','/versions/1/')+'?purpose=purchase_contract&limit=1',headers=headers)
        if native.status_code!=200 or native.json()['next_after']!=body['artifact_id']:
            raise AssertionError('Native reference page cursor changed')
        following=client.get(references.replace('/versions/2/','/versions/1/')+'?purpose=purchase_contract&limit=1&after='+body['artifact_id'],headers=headers)
        if following.status_code!=200 or len(following.json()['items'])!=1 or following.json()['next_after'] is not None:
            raise AssertionError('Native reference next page unavailable')
        choice=client.get(candidate,headers=headers)
        if choice.status_code!=200 or choice.json()['contract_version']!=2 or choice.json()['candidate']['verification_id']!=body['verification_id']:
            raise AssertionError('Mounted review candidate lost original source for new target')
        for target in (path,candidate):
            if client.get(target,headers=foreign_headers).status_code not in (401,403):
                raise AssertionError('Source-aware review crossed workspace boundary')
        drops['rpc/record_contract_review']=True
        lost=client.post(path,json=body,headers=headers)
        retry=client.post(path,json=body,headers=headers)
        if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate'] or retry.json()['approval_current']:
            raise AssertionError('Source-aware review exact commit-loss recovery failed')
        state=client.get(path,headers=headers)
        if state.status_code!=200 or not state.json()['approval_current'] or state.json()['execution_authorized']:
            raise AssertionError('New target review unavailable or execution inferred')
        if client.get(path.replace('/versions/2/','/versions/1/'),headers=headers).json()['approval_current']:
            raise AssertionError('Original version review became current again')
        if client.post(path,json=body,headers=foreign_headers).status_code not in (401,403):
            raise AssertionError('Source-aware review write crossed workspace')
    if db.query('SELECT contract_version,source_version FROM public.acquisition_contract_reviews WHERE id=%s',[body['id']])!=[{'contract_version':2,'source_version':1}]:
        raise AssertionError('Review did not retain separate target/source foreign keys')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_review' AND entity_id=%s",[body['id']])!=[{'n':1}]:
        raise AssertionError('Source-aware review retry duplicated audit')
    return path,body


def verify_source_review_revocation_http(db,app,drops,headers,path,body):
    with TestClient(app) as client:
        references=path.rsplit('/reviews/',1)[0]+'/references?purpose=purchase_contract'
        listed=client.get(references,headers=headers)
        if listed.status_code!=200 or listed.json()['items'][0]['status']!='requires_review' or listed.json()['items'][0]['verification_id'] is not None:
            raise AssertionError('Mounted source references retained revoked verification')
        state=client.get(path,headers=headers)
        candidate=client.get(path+'/documents/'+body['artifact_id']+'/candidate',headers=headers)
        if state.status_code!=200 or state.json()['approval_current'] or candidate.status_code!=200 or candidate.json()['candidate'] is not None:
            raise AssertionError('Revoked original evidence retained new-target approval')
        if candidate.json()['withdrawal']['review_id']!=body['id']:
            raise AssertionError('Original reviewer lost withdrawal after source revocation')
        withdrawal=body|{'id':'af920000-0000-4000-8000-000000000002','expected_sequence':1,
                         'status':'withdrawn','expires_at':None,'personally_reviewed':False}
        drops['rpc/record_contract_review']=True
        lost=client.post(path,json=withdrawal,headers=headers)
        retry=client.post(path,json=withdrawal,headers=headers)
        if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate'] or retry.json()['status']!='withdrawn':
            raise AssertionError('New-target withdrawal recovery failed after source revocation')
        if client.get(path,headers=headers).json()['status']!='withdrawn':
            raise AssertionError('Source-aware withdrawal not reflected in current state')
    if db.query('SELECT contract_version,source_version FROM public.acquisition_contract_reviews WHERE id=%s',[withdrawal['id']])!=[{'contract_version':2,'source_version':1}]:
        raise AssertionError('Withdrawal lost original source version')
