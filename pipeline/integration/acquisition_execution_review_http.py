"""Execution review through mounted API, actual local PostgREST and real RLS."""
from datetime import datetime,timedelta,timezone
from fastapi.testclient import TestClient

POLICY='af970000-0000-4000-8000-000000000001'
REVIEW='af970000-0000-4000-8000-000000000002'
WITHDRAW='af970000-0000-4000-8000-000000000003'


def verify_execution_http(db,app,drops,headers,foreign,workspace,contract,basis):
    path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/3/execution-review'
    terms=db.query('SELECT terms FROM public.acquisition_contract_versions WHERE deal_id=%s AND version=3',[contract])[0]['terms']
    # Local fixture provisioning only; there is no application policy-write path.
    db.query("""INSERT INTO private.acquisition_contract_review_policies(id,workspace_id,kind,purpose,reviewer_id,
        max_review_seconds,valid_from,valid_until,reviewed_by,approval_ref)
        SELECT %s,workspace_id,'executed_contract','purchase_contract',reviewer_id,max_review_seconds,
        valid_from,valid_until,reviewed_by,approval_ref FROM private.acquisition_contract_review_policies WHERE id=%s""",[POLICY,basis['policy_id']])
    body=dict(id=REVIEW,expected_version=3,expected_sequence=0,status='approved',artifact_id=basis['artifact_id'],
        verification_id=basis['verification_id'],policy_id=POLICY,
        expires_at=(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat(),personally_reviewed=True,
        note='Synthetic personal execution findings; no agreement signed or status changed by this test.',
        findings={**{name:{'finding':'confirmed','locator':'Synthetic signature clause',
            'note':'Synthetic test evidence only, never a legal finding.'}
            for name in ('seller_signatures','buyer_signatures','signing_authority','complete_agreement')},'terms':terms})
    history=db.query('SELECT version,terms FROM public.acquisition_contract_versions WHERE deal_id=%s ORDER BY version',[contract])
    with TestClient(app) as client:
        initial=client.get(path,headers=headers)
        if initial.status_code!=200 or initial.json()['status']!='not_reviewed':
            raise AssertionError('Execution initial state unavailable')
        for identity in (foreign,{}):
            for method in ('get','post'):
                response=getattr(client,method)(path,headers=identity,**({'json':body} if method=='post' else {}))
                if response.status_code not in (401,403):raise AssertionError('Execution review crossed workspace/session')
        drops['rpc/record_execution_review']=True
        lost=client.post(path,json=body,headers=headers)
        retry=client.post(path,json=body,headers=headers)
        if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate']:
            raise AssertionError(f'Execution review commit-loss recovery failed: {lost.status_code} {retry.status_code} {retry.text}')
        if lost.headers.get('X-Acquisition-Execution-Review-Rejected') or retry.json()['approval_current'] or retry.json()['execution_authorized']:
            raise AssertionError('Execution historical receipt claimed authority')
        current=client.get(path,headers=headers)
        if current.status_code!=200 or not current.json()['approval_current'] or current.json()['review_id']!=REVIEW:
            raise AssertionError('Execution current exact source state unavailable')
        changed=client.post(path,json=body|{'note':'Changed findings context cannot replace the exact recorded request.'},headers=headers)
        if changed.status_code!=409 or changed.headers.get('X-Acquisition-Execution-Review-Rejected')!='true':
            raise AssertionError('Execution conflicting request was not definitively rejected')
    if history!=db.query('SELECT version,terms FROM public.acquisition_contract_versions WHERE deal_id=%s ORDER BY version',[contract]):
        raise AssertionError('Execution evidence rewrote prepared terms')
    if db.query('SELECT acquisition_status FROM public.deals WHERE id=%s',[contract])!=[{'acquisition_status':'pending_signature'}]:
        raise AssertionError('Execution review advanced lifecycle')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_review' AND entity_id=%s",[REVIEW])!=[{'n':1}]:
        raise AssertionError('Execution exact recovery duplicated audit')
    return path,body


def verify_execution_revocation_http(db,app,drops,headers,path,body):
    db.query('UPDATE private.acquisition_activation SET enabled=false WHERE singleton')
    try:
        with TestClient(app) as client:
            state=client.get(path,headers=headers)
            if state.status_code!=200 or state.json()['status']!='requires_review' or state.json()['approval_current']:
                raise AssertionError('Execution review retained authority after source revocation/pause')
            if not client.post(path,json=body,headers=headers).json()['duplicate']:
                raise AssertionError('Execution historical recovery lost after pause')
            withdrawal=body|dict(id=WITHDRAW,expected_sequence=1,status='withdrawn',expires_at=None,personally_reviewed=False,findings=None)
            drops['rpc/record_execution_review']=True
            lost=client.post(path,json=withdrawal,headers=headers)
            retry=client.post(path,json=withdrawal,headers=headers)
            if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate'] or retry.json()['status']!='withdrawn':
                raise AssertionError('Execution withdrawal commit-loss recovery failed')
            if client.get(path,headers=headers).json()['status']!='withdrawn':
                raise AssertionError('Execution withdrawal state missing')
    finally:db.query('UPDATE private.acquisition_activation SET enabled=true WHERE singleton')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_review' AND entity_id=%s",[WITHDRAW])!=[{'n':1}]:
        raise AssertionError('Execution withdrawal duplicated audit')
