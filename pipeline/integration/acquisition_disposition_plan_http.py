"""Mounted purchase-path proposal journey against the real local gateway."""
from fastapi.testclient import TestClient


def verify_disposition_plan_http(db, app, drops, headers, token, workspace, contract, other):
    path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/2/disposition-plan'
    first,second,withdraw=[f'ae103000-0000-4000-8000-{n:012d}' for n in range(1,4)]
    body=dict(id=first,expected_version=2,expected_sequence=0,status='proposed',exit_type='principal_acquisition',
        original_plan_id=None,note='Synthetic internal principal purchase proposal, requiring later approvals.')
    original=db.query('SELECT to_jsonb(d) AS row FROM public.deals d WHERE id=%s',[contract])
    with TestClient(app) as client:
        state=client.get(path,headers=headers)
        if state.status_code!=200 or state.json()['readiness']!='ready_for_planning':
            raise AssertionError('Mounted purchase-path state unavailable: '+str(state.status_code))
        drops['rpc/record_disposition_plan']=True
        lost=client.post(path,json=body,headers=headers)
        retry=client.post(path,json=body,headers=headers)
        if lost.status_code!=503 or 'x-acquisition-disposition-plan-rejected' in lost.headers or retry.status_code!=200 or not retry.json()['duplicate']:
            raise AssertionError('Mounted purchase-path committed-response recovery failed')
        if retry.json()['disposition_approved'] or retry.json()['execution_authorized']:
            raise AssertionError('Proposal receipt implied disposition authority')
        conflict=client.post(path,json=body|dict(exit_type='wholesale_assignment'),headers=headers)
        if conflict.status_code!=409 or conflict.headers.get('x-acquisition-disposition-plan-rejected')!='true':
            raise AssertionError('Mounted proposal conflict not definite')
        for denied in ({}, {'Authorization':'Bearer '+token(other)}, {'Authorization':'Bearer '+token(role='service_role')}):
            for response in (client.get(path,headers=denied),client.post(path,json=body,headers=denied)):
                if response.status_code not in (401,403):raise AssertionError('Mounted proposal escaped workspace/role access')
        if client.post(path.replace('/versions/2/','/versions/1/'),json=body,headers=headers).status_code!=409:
            raise AssertionError('Proposal moved to another version')
        revised=body|dict(id=second,expected_sequence=1,exit_type='wholesale_assignment')
        if client.post(path,json=revised,headers=headers).status_code!=200:
            raise AssertionError('Internal assignment proposal unavailable')
        db.query('UPDATE private.acquisition_activation SET enabled=false')
        try:
            state=client.get(path,headers=headers)
            if state.status_code!=200 or state.json()['readiness']!='paused' or state.json()['withdrawal']['plan_id']!=second:
                raise AssertionError('Paused proposal lost original withdrawal')
            if not client.post(path,json=body,headers=headers).json()['duplicate']:
                raise AssertionError('Original proposal retry lost after pause')
            invalid=client.post(path,json=revised|dict(id=withdraw,expected_sequence=2),headers=headers)
            if invalid.status_code!=409:raise AssertionError('Paused new proposal accepted')
            cancelled=revised|dict(id=withdraw,expected_sequence=2,status='withdrawn',original_plan_id=second)
            drops['rpc/record_disposition_plan']=True
            lost=client.post(path,json=cancelled,headers=headers)
            recovered=client.post(path,json=cancelled,headers=headers)
            if lost.status_code!=503 or recovered.status_code!=200 or not recovered.json()['duplicate']:
                raise AssertionError('Original proposal withdrawal recovery failed')
            current=client.get(path,headers=headers).json()
            if current['latest']['status']!='withdrawn' or current['withdrawal'] is not None:
                raise AssertionError('Withdrawal did not supersede original proposal')
        finally:db.query('UPDATE private.acquisition_activation SET enabled=true')
    if db.query('SELECT to_jsonb(d) AS row FROM public.deals d WHERE id=%s',[contract])!=original:
        raise AssertionError('Proposal changed canonical contract status, buyer, price or closing fields')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_disposition_plan' AND entity_id IN (%s,%s,%s)",[first,second,withdraw])!=[{'n':3}]:
        raise AssertionError('Mounted proposals duplicated or omitted original audit')
