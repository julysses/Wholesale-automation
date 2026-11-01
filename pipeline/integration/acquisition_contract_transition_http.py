"""Actual user-JWT lifecycle RPC through mounted API; no signature or delivery."""
from fastapi.testclient import TestClient

TRANSITION='af950000-0000-4000-8000-000000000001'


def verify_transition_http(db,app,drops,headers,foreign,workspace,contract):
    path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/transitions'
    body=dict(id=TRANSITION,expected_version=3,expected_sequence=0,expected_status='draft',target_status='pending_signature',
              reason='Synthetic human request to record awaiting signature, without signing or sending.')
    before=db.query('SELECT version,status,terms FROM public.acquisition_contract_versions WHERE deal_id=%s ORDER BY version',[contract])
    with TestClient(app) as client:
        for identity in (foreign,{}):
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
