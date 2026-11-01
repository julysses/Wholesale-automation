"""Actual user-JWT lifecycle RPC through mounted API; no signature or delivery."""
from fastapi.testclient import TestClient

TRANSITION='af950000-0000-4000-8000-000000000001'


def verify_transition_http(db,app,drops,headers,foreign,workspace,contract):
    path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/transitions'
    body=dict(id=TRANSITION,expected_version=3,expected_sequence=0,expected_status='draft',target_status='pending_signature',
              reason='Synthetic human request to record awaiting signature, without signing or sending.')
    before=db.query('SELECT version,status,terms FROM public.acquisition_contract_versions WHERE deal_id=%s ORDER BY version',[contract])
    with TestClient(app) as client:
        choice=client.get(path+'/candidate',params={'contract_version':3},headers=headers)
        if choice.status_code!=200 or choice.headers.get('cache-control')!='no-store' or choice.json()['status']!='ready_for_human_review':
            raise AssertionError('Lifecycle discovery did not provide a fresh exact handoff')
        selected=choice.json()['candidate']
        if selected['expected_version']!=3 or selected['expected_sequence']!=0 or selected['target_status']!='pending_signature':
            raise AssertionError('Lifecycle discovery mixed terms and status cursors')
        for identity in (foreign,{}):
            if client.get(path+'/candidate',params={'contract_version':3},headers=identity).status_code not in (401,403):
                raise AssertionError('Lifecycle discovery crossed workspace/session')
            if client.post(path,json=body,headers=identity).status_code not in (401,403):
                raise AssertionError('Lifecycle request crossed workspace/session')
        drops['rpc/record_contract_transition']=True
        lost=client.post(path,json=body,headers=headers)
        retry=client.post(path,json=body,headers=headers)
        if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate']:
            raise AssertionError(f'Lifecycle committed-response recovery failed: {lost.status_code} {retry.status_code}')
        if lost.headers.get('X-Acquisition-Transition-Rejected') or retry.json()['execution_authorized']:
            raise AssertionError('Lifecycle receipt claimed current execution authority')
        if retry.json()['contract_version']!=3 or retry.json()['sequence']!=1 or retry.json()['recorded_status']!='pending_signature':
            raise AssertionError('Lifecycle cursor corrupted terms version')
        recorded=client.get(path+'/candidate',params={'contract_version':3},headers=headers)
        if recorded.status_code!=200 or recorded.json()['status']!='execution_review_required' or recorded.json()['candidate'] is not None or recorded.json()['sequence']!=1:
            raise AssertionError('Lifecycle discovery offered a duplicate transition after save')
        changed=client.post(path,json=body|{'reason':'Different reason cannot confirm the original lifecycle change.'},headers=headers)
        if changed.status_code!=409 or changed.headers.get('X-Acquisition-Transition-Rejected')!='true':
            raise AssertionError('Conflicting transition request was not definitively rejected')
        listed=client.get(f'/api/acquisition/workspaces/{workspace}/contracts/drafts',headers=headers)
        if listed.status_code!=200 or not any(r['id']==contract and r['acquisition_status']=='pending_signature' for r in listed.json()['items']):
            raise AssertionError('Contract disappeared from guided workflow after transition')
    if before!=db.query('SELECT version,status,terms FROM public.acquisition_contract_versions WHERE deal_id=%s ORDER BY version',[contract]):
        raise AssertionError('Lifecycle transition rewrote terms history')
    if db.query('SELECT acquisition_status,stage FROM public.deals WHERE id=%s',[contract])!=[{'acquisition_status':'pending_signature','stage':'offer_made'}]:
        raise AssertionError('Lifecycle transition implied a signed contract or buyer marketing')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_transition' AND entity_id=%s",[TRANSITION])!=[{'n':1}]:
        raise AssertionError('Lifecycle retry duplicated audit')


def verify_executed_transition_http(db,app,drops,headers,foreign,workspace,contract):
    path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/transitions'
    request_id='af950000-0000-4000-8000-000000000002'
    body=dict(id=request_id,expected_version=3,expected_sequence=1,expected_status='pending_signature',target_status='executed',
              reason='Synthetic human status recording from independently reviewed execution evidence.')
    history=db.query('SELECT version,status,terms FROM public.acquisition_contract_versions WHERE deal_id=%s ORDER BY version',[contract])
    with TestClient(app) as client:
        choice=client.get(path+'/candidate',params={'contract_version':3},headers=headers)
        if choice.status_code!=200 or choice.json()['candidate']['target_status']!='executed' or choice.json()['candidate']['expected_sequence']!=1:
            raise AssertionError('Fresh executed transition choice unavailable')
        for identity in (foreign,{}):
            if client.post(path,json=body,headers=identity).status_code not in (401,403):
                raise AssertionError('Executed status crossed workspace/session')
        drops['rpc/record_contract_transition']=True
        lost=client.post(path,json=body,headers=headers)
        retry=client.post(path,json=body,headers=headers)
        if lost.status_code!=503 or retry.status_code!=200 or not retry.json()['duplicate']:
            raise AssertionError(f'Executed status exact recovery failed: {lost.status_code} {retry.status_code} {retry.text}')
        receipt=retry.json()
        if lost.headers.get('X-Acquisition-Transition-Rejected') or receipt['execution_authorized'] or receipt['sequence']!=2 or receipt['recorded_status']!='executed':
            raise AssertionError('Executed historical receipt changed authority or cursor')
        if client.post(path,json=body|{'reason':'A changed reason cannot replace the original execution record.'},headers=headers).status_code!=409:
            raise AssertionError('Executed request conflict accepted')
        listed=client.get(f'/api/acquisition/workspaces/{workspace}/contracts/drafts',headers=headers)
        if listed.status_code!=200 or not any(row['id']==contract and row['acquisition_status']=='executed' for row in listed.json()['items']):
            raise AssertionError('Executed contract disappeared from scoped history')
        held=client.get(path+'/candidate',params={'contract_version':3},headers=headers)
        if held.status_code!=200 or held.json()['current_status']!='executed' or held.json()['status']!='ready_for_human_review' or held.json()['candidate']['target_status']!='title_review' or held.json()['candidate']['expected_sequence']!=2:
            raise AssertionError('Executed status did not offer the controlled title-review handoff')
    if history!=db.query('SELECT version,status,terms FROM public.acquisition_contract_versions WHERE deal_id=%s ORDER BY version',[contract]):
        raise AssertionError('Executed transition rewrote terms')
    if db.query('SELECT acquisition_status,stage FROM public.deals WHERE id=%s',[contract])!=[{'acquisition_status':'executed','stage':'offer_made'}]:
        raise AssertionError('Executed status incorrectly altered legacy pipeline')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_transition' AND entity_id=%s",[request_id])!=[{'n':1}]:
        raise AssertionError('Executed retry duplicated audit')
