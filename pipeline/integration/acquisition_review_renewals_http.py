"""Real gateway renewal recovery without changing the recorded contract handoff."""
from datetime import datetime, timedelta, timezone


def verify_review_renewal_http(db, client, drops, headers, token, workspace, contract, other, root, request_id='af126000-0000-4000-8000-000000000001'):
    path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/2/review-renewals'
    before=db.query('SELECT to_jsonb(r) AS row FROM public.acquisition_contract_reviews r WHERE id=%s',[root])
    transitions=db.query('SELECT to_jsonb(t) AS row FROM public.acquisition_contract_transitions t WHERE contract_id=%s ORDER BY sequence',[contract])
    index=client.get(path,headers=headers)
    if index.status_code!=200 or index.headers.get('cache-control')!='no-store' or index.json()['execution_authorized']:
        raise AssertionError('Renewal index unavailable: '+str(index.status_code))
    if not any(r['root_review_id']==root for r in index.json()['items']):
        raise AssertionError('Renewal index omitted the original review')
    route=path+'/'+root+'/candidate'
    selected=client.get(route,headers=headers)
    if selected.status_code!=200 or selected.headers.get('cache-control')!='no-store':
        raise AssertionError('Renewal candidate unavailable: '+str(selected.status_code))
    data=selected.json();candidate=data['candidate']
    if data['status']!='ready_for_human_review' or not candidate or data['execution_authorized']:
        raise AssertionError('Renewal candidate unexpectedly held: '+data['status'])
    expiry=min(datetime.now(timezone.utc)+timedelta(minutes=2),datetime.fromisoformat(candidate['max_expires_at'].replace('Z','+00:00'))-timedelta(seconds=1))
    request=dict(id=request_id,expected_version=2,
        expected_sequence=candidate['expected_sequence'],kind=data['kind'],deadline_term=data['deadline_term'],
        root_review_id=root,previous_review_id=candidate['previous_review_id'],policy_id=candidate['policy_id'],
        expected_snapshot_sha256=candidate['expected_snapshot_sha256'],expires_at=expiry.isoformat(),
        personally_reviewed=True,note='Personally rechecked the unchanged original findings and supporting evidence for renewal.')
    for denied in ({},{'Authorization':'Bearer '+token(other)},{'Authorization':'Bearer '+token(role='service_role')}):
        for response in (client.get(path,headers=denied),client.get(route,headers=denied),client.post(path,json=request,headers=denied)):
            if response.status_code not in (401,403):raise AssertionError('Renewal escaped workspace or user authorization')
    drops['rpc/record_acquisition_review_renewal']=True
    lost=client.post(path,json=request,headers=headers)
    recovered=client.post(path,json=request,headers=headers)
    if lost.status_code!=503 or lost.headers.get('X-Acquisition-Renewal-Rejected') or recovered.status_code!=200:
        raise AssertionError('Renewal commit-loss recovery failed: '+str((lost.status_code,recovered.status_code,recovered.text)))
    receipt=recovered.json()
    if not receipt['duplicate'] or receipt['approval_current'] or receipt['execution_authorized'] or receipt['review_id']!=request['id']:
        raise AssertionError('Renewal recovery was not an exact historical receipt')
    changed=client.post(path,json=request|dict(note='A changed request must not replace the saved original renewal.'),headers=headers)
    if changed.status_code!=409:raise AssertionError('Renewal accepted a changed retry')
    if client.post(path,json=request|dict(findings={}),headers=headers).status_code!=422:
        raise AssertionError('Renewal accepted replacement findings')
    current=client.get(path,headers=headers)
    if current.status_code!=200 or next(r for r in current.json()['items'] if r['root_review_id']==root)['current_review']['review_id']!=request['id']:
        raise AssertionError('Renewal index lost the appended review')
    if before!=db.query('SELECT to_jsonb(r) AS row FROM public.acquisition_contract_reviews r WHERE id=%s',[root]):
        raise AssertionError('Renewal rewrote original findings')
    if transitions!=db.query('SELECT to_jsonb(t) AS row FROM public.acquisition_contract_transitions t WHERE contract_id=%s ORDER BY sequence',[contract]):
        raise AssertionError('Renewal rewrote original handoff')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_id=%s AND action='renewed'",[request['id']])!=[{'n':1}]:
        raise AssertionError('Renewal recovery duplicated the audit')
    return request['id'],receipt['sequence']
