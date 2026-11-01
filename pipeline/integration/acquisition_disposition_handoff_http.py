"""Actual disposition handoff with retained originals and exact commit-loss retry."""
from fastapi.testclient import TestClient
from acquisition_review_renewals_http import verify_review_renewal_http


def verify_disposition_handoff_http(db,app,drops,headers,token,workspace,contract,admin,other,review_body):
    path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/transitions'
    review_path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/2/disposition-review'
    policy,review,transition=[f'af122000-0000-4000-8000-{n:012d}' for n in range(1,4)]
    before=db.query('SELECT version,status,terms FROM public.acquisition_contract_versions WHERE deal_id=%s ORDER BY version',[contract])
    # New, separate synthetic approval rather than undoing the revoked original scope.
    db.query("INSERT INTO private.acquisition_contract_review_policies SELECT (jsonb_populate_record(NULL::private.acquisition_contract_review_policies,to_jsonb(p)||jsonb_build_object('id',%s::text))).* FROM private.acquisition_contract_review_policies p WHERE id=%s",[policy,review_body['policy_id']])
    db.query("INSERT INTO private.acquisition_disposition_policy_scopes(policy_id,workspace_id,reviewer_id,exit_type,legal_source_id,reviewed_by,approval_ref,valid_from,valid_until) SELECT %s,workspace_id,reviewer_id,exit_type,legal_source_id,reviewed_by,%s,valid_from,valid_until FROM private.acquisition_disposition_policy_scopes WHERE policy_id=%s",[policy,policy,review_body['policy_id']])
    approval=review_body|dict(id=review,expected_sequence=3,policy_id=policy)
    body=dict(id=transition,expected_version=2,expected_sequence=3,expected_status='title_review',target_status='disposition_review',
        reason='Record the original reviewed assignment proposal for separate disposition steps.')
    with TestClient(app) as client:
        held=client.get(path+'/candidate',params={'contract_version':2},headers=headers)
        if held.status_code!=200 or held.json()['status']!='disposition_review_required' or held.json()['candidate'] is not None:
            raise AssertionError('Missing disposition approval did not hold the handoff')
        approved=client.post(review_path,json=approval,headers=headers)
        if approved.status_code!=200:raise AssertionError('Handoff fixture approval failed: '+str(approved.status_code))
        before_handoff,_=verify_review_renewal_http(db,client,drops,headers,token,workspace,contract,other,review)
        choice=client.get(path+'/candidate',params={'contract_version':2},headers=headers)
        if choice.status_code!=200 or choice.headers.get('cache-control')!='no-store':raise AssertionError('Disposition handoff choice unavailable')
        selected=choice.json()['candidate']
        roots=db.query('SELECT disposition_title_review_id::text,disposition_execution_id::text FROM public.acquisition_contract_reviews WHERE id=%s',[review])[0]
        execution=db.query('SELECT execution_review_id::text FROM public.acquisition_contract_transitions WHERE id=%s',[roots['disposition_execution_id']])[0]['execution_review_id']
        if selected is None or selected['disposition_review_id']!=review or selected['plan_id']!=approval['plan_id'] or selected['title_review_id']!=roots['disposition_title_review_id'] or selected['execution_review_id']!=execution or selected['exit_type']!='wholesale_assignment' or selected['expected_sequence']!=3:
            raise AssertionError('Disposition handoff lost its original approval chain')
        for identity in ({},{'Authorization':'Bearer '+token(other)},{'Authorization':'Bearer '+token(role='service_role')}):
            for response in (client.get(path+'/candidate',params={'contract_version':2},headers=identity),client.post(path,json=body,headers=identity)):
                if response.status_code not in (401,403):raise AssertionError('Disposition handoff escaped user/workspace authorization')
        drops['rpc/record_contract_transition']=True
        lost=client.post(path,json=body,headers=headers);retry=client.post(path,json=body,headers=headers)
        if lost.status_code!=503 or lost.headers.get('X-Acquisition-Transition-Rejected') or retry.status_code!=200 or not retry.json()['duplicate']:
            raise AssertionError('Disposition handoff commit-loss recovery failed: '+str(retry.status_code))
        used=db.query("SELECT new_value->'review_authority' AS used FROM public.audit_logs WHERE entity_id=%s AND entity_type='acquisition_contract_transition'",[transition])[0]['used']
        if not any(row['root_id']==review and row['review_id']==before_handoff for row in used):
            raise AssertionError('Handoff audit did not retain the actual renewed approval')
        if retry.json()['recorded_status']!='disposition_review' or retry.json()['sequence']!=4 or retry.json()['execution_authorized']:
            raise AssertionError('Disposition receipt changed status or granted execution')
        if client.post(path,json=body|dict(reason='Changed reason cannot replace original handoff history.'),headers=headers).status_code!=409:
            raise AssertionError('Disposition handoff accepted a changed retry')
        done=client.get(path+'/candidate',params={'contract_version':2},headers=headers)
        if done.status_code!=200 or done.json()['status']!='disposition_review_started' or done.json()['candidate'] is not None:
            raise AssertionError('Completed disposition handoff still offered an action')
        listed=client.get(f'/api/acquisition/workspaces/{workspace}/contracts/drafts',headers=headers)
        if listed.status_code!=200 or not any(r['id']==contract and r['acquisition_status']=='disposition_review' for r in listed.json()['items']):
            raise AssertionError('Disposition contract disappeared from guided history')
        current=client.get(review_path,headers=headers)
        if current.status_code!=200 or not current.json()['approval_current']:raise AssertionError('Handoff immediately invalidated original disposition authority')
        renewed,renewed_sequence=verify_review_renewal_http(db,client,drops,headers,token,workspace,contract,other,review,request_id='af126000-0000-4000-8000-000000000002')
        db.query('UPDATE private.acquisition_activation SET enabled=false')
        try:
            paused=client.get(path+'/candidate',params={'contract_version':2},headers=headers)
            if paused.status_code!=200 or paused.json()['status']!='paused' or paused.json()['candidate'] is not None:raise AssertionError('Paused handoff offered execution')
            if not client.post(path,json=body,headers=headers).json()['duplicate']:raise AssertionError('Pause erased original handoff recovery')
            title_path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/2/title-review'
            title_options=client.get(title_path+'/candidate',headers=headers)
            if title_options.status_code!=200 or title_options.json()['candidate'] is not None or title_options.json()['resolution'] is not None:
                raise AssertionError('Post-handoff original title choices unavailable')
            title_original=title_options.json()['withdrawal']
            if not title_original or title_original['review_id']!=roots['disposition_title_review_id']:
                raise AssertionError('Post-handoff title withdrawal changed the original')
            title_withdrawal=dict(id='af124000-0000-4000-8000-000000000001',expected_version=2,
                expected_sequence=title_original['expected_sequence'],status='withdrawn',artifact_id=title_original['artifact_id'],
                verification_id=title_original['verification_id'],policy_id=title_original['policy_id'],expires_at=None,
                personally_reviewed=False,findings=None,note='Withdraw the original title findings after disposition handoff.')
            drops['rpc/record_title_review']=True
            lost=client.post(title_path,json=title_withdrawal,headers=headers);recovered=client.post(title_path,json=title_withdrawal,headers=headers)
            if lost.status_code!=503 or recovered.status_code!=200 or not recovered.json()['duplicate']:
                raise AssertionError('Post-handoff title withdrawal recovery failed')
            if client.get(title_path,headers=headers).json()['status']!='withdrawn':raise AssertionError('Title withdrawal not current')
            title_history=client.get(title_path+'/history/'+title_original['review_id'],headers=headers)
            if title_history.status_code!=200 or title_history.json()['record']['status']!='approved':raise AssertionError('Title withdrawal rewrote original findings')
            source=db.query('SELECT artifact_id::text FROM public.acquisition_contract_reviews WHERE id=%s',[execution])[0]['artifact_id']
            version_path=f'/api/acquisition/workspaces/{workspace}/contracts/{contract}/versions/2'
            for kind,route,rpc_name,request_id in (
                ('deadline',version_path+'/deadline-reviews/closing_deadline/documents/'+source+'/candidate','rpc/record_deadline_resolution_review','af125000-0000-4000-8000-000000000001'),
                ('execution',version_path+'/execution-review/documents/'+source+'/candidate','rpc/record_execution_review','af125000-0000-4000-8000-000000000002')):
                selected=client.get(route,headers=headers)
                if selected.status_code!=200 or selected.json()['candidate'] is not None or not selected.json()['withdrawal']:
                    raise AssertionError('Post-handoff '+kind+' original withdrawal unavailable')
                prior=selected.json()['withdrawal']
                command=dict(id=request_id,expected_version=2,expected_sequence=prior['expected_sequence'],status='withdrawn',
                    artifact_id=prior['artifact_id'],verification_id=prior['verification_id'],policy_id=prior['policy_id'],
                    expires_at=None,personally_reviewed=False,note='Withdraw the original '+kind+' review after disposition handoff.')
                if kind=='deadline':
                    command.update(term='closing_deadline',original_review_id=prior['review_id'],resolution=None)
                    write_path=version_path+'/deadline-reviews';state_path=write_path+'/closing_deadline'
                else:
                    if prior['review_id']!=db.query('SELECT private.acquisition_review_anchor_head(%s,%s,2,%s,clock_timestamp())::text AS id',[workspace,contract,execution])[0]['id']:raise AssertionError('Execution withdrawal changed the current personal review')
                    command.update(findings=None);write_path=version_path+'/execution-review';state_path=write_path
                drops[rpc_name]=True
                lost=client.post(write_path,json=command,headers=headers);recovered=client.post(write_path,json=command,headers=headers)
                if lost.status_code!=503 or recovered.status_code!=200 or not recovered.json()['duplicate']:
                    raise AssertionError('Post-handoff '+kind+' withdrawal recovery failed: '+str(recovered.status_code))
                state=client.get(state_path,headers=headers)
                if state.status_code!=200 or state.json()['status']!='withdrawn' or state.json()['approval_current']:
                    raise AssertionError('Post-handoff '+kind+' withdrawal retained current authority')
                if client.get(route,headers=headers).json()['withdrawal'] is not None:raise AssertionError('Repeated '+kind+' withdrawal offered')
            options=client.get(review_path+'/candidate',headers=headers)
            if options.status_code!=200 or options.json()['withdrawal']['review_id']!=renewed or options.json()['candidate'] is not None or options.json()['resolution'] is not None:
                raise AssertionError('Post-handoff pause lost independent original withdrawal')
            withdrawal=approval|dict(id='af122000-0000-4000-8000-000000000004',expected_sequence=renewed_sequence,status='withdrawn',original_review_id=renewed,
                expires_at=None,personally_reviewed=False,findings=None,note='Withdraw the original disposition approval after its recorded handoff.')
            drops['rpc/record_disposition_review']=True
            lost=client.post(review_path,json=withdrawal,headers=headers);recovered=client.post(review_path,json=withdrawal,headers=headers)
            if lost.status_code!=503 or recovered.status_code!=200 or not recovered.json()['duplicate']:
                raise AssertionError('Post-handoff original withdrawal recovery failed')
            state=client.get(review_path,headers=headers)
            if state.status_code!=200 or state.json()['status']!='withdrawn' or state.json()['approval_current']:
                raise AssertionError('Post-handoff withdrawal retained current authority')
            if not client.post(path,json=body,headers=headers).json()['duplicate']:raise AssertionError('Withdrawal erased original handoff receipt')
            original=client.get(review_path+'/history/'+review,headers=headers)
            if original.status_code!=200 or original.json()['record']['status']!='approved':raise AssertionError('Withdrawal rewrote original approved findings')
        finally:db.query('UPDATE private.acquisition_activation SET enabled=true')
    if before!=db.query('SELECT version,status,terms FROM public.acquisition_contract_versions WHERE deal_id=%s ORDER BY version',[contract]):raise AssertionError('Disposition handoff rewrote terms')
    if db.query('SELECT acquisition_status,stage FROM public.deals WHERE id=%s',[contract])!=[{'acquisition_status':'disposition_review','stage':'offer_made'}]:raise AssertionError('Disposition handoff changed legacy pipeline')
    if db.query('SELECT disposition_review_id::text,disposition_plan_id::text FROM public.acquisition_contract_transitions WHERE id=%s',[transition])!=[{'disposition_review_id':review,'disposition_plan_id':approval['plan_id']}]:raise AssertionError('Disposition ledger lost original approvals')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_transition' AND entity_id=%s",[transition])!=[{'n':1}]:raise AssertionError('Disposition retry duplicated audit')
