"""Sourced contract terms through the mounted API and actual local database gateway."""
from fastapi.testclient import TestClient


def verify_terms_http(db, app, document_drops, token, workspace, contract, artifact, digest, other, lead):
    path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}'
    headers={'Authorization':'Bearer '+token()}
    request_id='af910000-0000-4000-8000-000000000001'
    terms={'purchase_price_cents':14000000,'earnest_money_cents':None,'assignment_allowed':None,
           'assignment_provisions':None,'effective':{'precision':'date','calendar_date':'2026-11-01'},
           'inspection_deadline':{'precision':'unknown'},'closing_deadline':{'precision':'unknown'},
           'sources':[{'term':name,'artifact_id':artifact,'artifact_version':1,'sha256':digest,'locator':'Synthetic clause 1'}
                      for name in ('purchase_price','effective')],
           'note':'Synthetic sourced terms prepared for independent human review.'}
    body={'id':request_id,'expected_version':1,'terms':terms}
    document_drops['rpc/save_contract_terms']=True
    with TestClient(app) as client:
        lost=client.post(path+'/terms',json=body,headers=headers)
        recovered=client.post(path+'/terms',json=body,headers=headers)
        if lost.status_code!=503 or recovered.status_code!=200 or recovered.json()!={
                'request_id':request_id,'workspace_id':workspace,'contract_id':contract,'version':2,
                'status':'draft','duplicate':True,'execution_authorized':False}:
            raise AssertionError(f'Terms actual committed reply recovery failed: {lost.status_code} {recovered.status_code}')
        if lost.headers.get('X-Acquisition-Terms-Rejected') or recovered.headers.get('cache-control')!='no-store':
            raise AssertionError('Terms uncertain-save or cache boundary lost')
        first=client.get(path+'/versions?limit=1',headers=headers)
        second=client.get(path+'/versions?after=1&limit=1',headers=headers)
        if first.status_code!=200 or first.json()['next_after']!=1 or first.json()['items'][0]['terms'] is not None:
            raise AssertionError('Original contract version history lost')
        if second.status_code!=200 or second.json()['next_after'] is not None or second.json()['items'][0]['id']!=request_id:
            raise AssertionError('Sourced term history cursor or identity lost')
        saved=second.json()['items'][0]['terms']
        if saved['earnest_money_cents'] is not None or saved['effective']['instant'] is not None or saved['effective']['calendar_date']!='2026-11-01':
            raise AssertionError('Terms inferred money or date cutoff')
        if saved['sources']!=terms['sources'] or saved['inspection_deadline']['precision']!='unknown':
            raise AssertionError('Original source identity or unknown deadline lost')
        drafts=client.get(f'/api/acquisition/workspaces/{workspace}/contracts/drafts?lead_id={lead}',headers=headers)
        if drafts.status_code!=200 or drafts.json()['items'][0]['acquisition_version']!=2:
            raise AssertionError('Updated draft disappeared from the existing app list')
        review=client.get(path+'/versions/1/reviews/contract_review',headers=headers)
        if review.status_code!=200 or review.json()['approval_current']:
            raise AssertionError('Human approval carried to changed terms')
        conflict=client.post(path+'/terms',json=body|{'terms':terms|{'note':'Changed text must never replace an uncertain request.'}},headers=headers)
        stale=client.post(path+'/terms',json=body|{'id':'af910000-0000-4000-8000-000000000002'},headers=headers)
        if conflict.status_code!=409 or stale.status_code!=409 or conflict.headers.get('X-Acquisition-Terms-Rejected')!='true':
            raise AssertionError('Terms request conflict or expected version check bypassed')
        for identity in ({'Authorization':'Bearer '+token(other)},{}):
            if client.post(path+'/terms',json=body,headers=identity).status_code not in (401,403):
                raise AssertionError('Terms write workspace/session bypass')
            result=client.get(path+'/versions',headers=identity)
            if not (result.status_code in (401,403) or result.status_code==200 and result.json()['items']==[]):
                raise AssertionError('Terms history leaked across workspace/session')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_terms' AND entity_id=%s",[request_id])!=[{'n':1}]:
        raise AssertionError('Terms recovery duplicated immutable audit')
    if db.query('SELECT count(*) AS n FROM public.acquisition_contract_term_sources WHERE workspace_id=%s AND contract_id=%s AND contract_version=2',[workspace,contract])!=[{'n':2}]:
        raise AssertionError('Terms did not retain exact original source links')
    return path,body


def verify_terms_revocation_http(app, token, path, body):
    with TestClient(app) as client:
        headers={'Authorization':'Bearer '+token()}
        retry=client.post(path+'/terms',json=body,headers=headers)
        rejected=client.post(path+'/terms',json=body|{'id':'af910000-0000-4000-8000-000000000003','expected_version':2},headers=headers)
        if retry.status_code!=200 or not retry.json()['duplicate'] or retry.json()['execution_authorized'] or rejected.status_code!=409:
            raise AssertionError('Revoked source must allow historical recovery but deny a new sourced version')
