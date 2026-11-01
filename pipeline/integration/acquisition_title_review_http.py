"""Title RPC through real local PostgREST, with synthetic signed evidence only."""
from dataclasses import replace
from datetime import datetime,timezone
from uuid import UUID
from tools.acquisition_contract_attestation import build_contract_scan_attestation


def verify_title_review_http(db,rpc,request,token,workspace,contract,document,admin,other,key,observed,review_policy,expiry):
    scan,policy,review,hold,withdrawal=[f'ae980000-0000-4000-8000-{n:012d}' for n in range(1,6)]
    db.query("INSERT INTO private.acquisition_contract_verification_key_scopes(workspace_id,key_id,purpose,reviewed_by,approval_ref,valid_from,valid_until) VALUES(%s,%s,'title_report',%s,%s,clock_timestamp()-interval '1 hour',clock_timestamp()+interval '1 hour')",[workspace,str(key.id),admin,document])
    state=rpc('contract_document_state',dict(p_workspace=workspace,p_contract=contract,p_version=2,p_artifact=document))
    evidence=observed|{name:state[name] for name in ('workspace_id','contract_id','contract_version','artifact_id','purpose','media_type','retain_until','retention_policy_id','checked_at')}
    evidence.update(sha256='b'*64,byte_size=123,scan_checked_at=state['checked_at'],registry_checked_at=state['checked_at'])
    signed=build_contract_scan_attestation(evidence,request_id=UUID(scan),actor_id=UUID(admin),session_id=UUID(admin),key=replace(key,purposes=frozenset({'title_report'})),clock=lambda:datetime.now(timezone.utc))
    rpc('record_contract_document_verification',signed)
    db.query("INSERT INTO private.acquisition_contract_review_policies SELECT (jsonb_populate_record(NULL::private.acquisition_contract_review_policies,to_jsonb(p)||jsonb_build_object('id',%s::text,'kind','title_findings','purpose','title_report','title_report_max_age_days',1,'title_report_timezone','UTC'))).* FROM private.acquisition_contract_review_policies p WHERE id=%s",[policy,review_policy])
    source=dict(artifact_id=document,artifact_version=2,sha256='b'*64,locator='Synthetic title report, schedule A')
    findings=dict(report_as_of=dict(precision='date',calendar_date=datetime.now(timezone.utc).date().isoformat(),instant=None),report_as_of_source=source,report_note='Synthetic report cutoff preserved as a calendar date.',
        **{name:dict(finding='satisfactory',note='Synthetic human-reviewed original title finding.',required_action=None,sources=[source]) for name in ('ownership','legal_description','liens_and_payoffs','exceptions_and_encumbrances','occupancy_and_possession')})
    body=dict(p_id=review,p_workspace=workspace,p_contract=contract,p_version=2,p_expected_sequence=0,p_status='approved',p_artifact=document,p_verification=scan,p_policy=policy,p_expires=expiry,p_personally_reviewed=True,p_note='Synthetic title findings reviewed with original evidence and execution.',p_findings=findings)
    rpc('record_title_review',body)  # Discard a committed reply, then recover exact request.
    recovered=rpc('record_title_review',body)
    if not recovered['duplicate'] or recovered['approval_current'] or recovered['execution_authorized']:raise AssertionError('Title gateway recovery implied authority')
    context=dict(p_workspace=workspace,p_contract=contract,p_version=2)
    if not rpc('title_review_state',context)['approval_current']:raise AssertionError('Title gateway did not retain current exact review')
    for who in (token(other),token(role='service_role')):
        for name,payload in (('record_title_review',body),('title_review_state',context)):
            status,_=request('/rpc/'+name,who,payload)
            if status not in (401,403):raise AssertionError('Title gateway scope or role bypass')
    status,_=request('/rpc/record_title_review',token(),body|dict(p_note='Different request text cannot replace an original title review.'))
    if status!=409:raise AssertionError('Title gateway request conflict accepted')
    hold_body=body|dict(p_id=hold,p_expected_sequence=1,p_status='requires_resolution',p_expires=None)
    rpc('record_title_review',hold_body)
    if rpc('title_review_state',context)['status']!='requires_resolution':raise AssertionError('Title hold failed to supersede approval')
    db.query('UPDATE private.acquisition_activation SET enabled=false')
    try:
        if not rpc('record_title_review',body)['duplicate']:raise AssertionError('Paused title receipt disappeared')
        withdrawal_body=hold_body|dict(p_id=withdrawal,p_expected_sequence=2,p_status='withdrawn',p_personally_reviewed=False,p_findings=None)
        rpc('record_title_review',withdrawal_body)
        if not rpc('record_title_review',withdrawal_body)['duplicate'] or rpc('title_review_state',context)['status']!='withdrawn':raise AssertionError('Original title withdrawal failed')
    finally:db.query('UPDATE private.acquisition_activation SET enabled=true')
    if db.query("SELECT count(*) AS n FROM public.audit_logs WHERE entity_type='acquisition_contract_review' AND entity_id IN (%s,%s,%s)",[review,hold,withdrawal])!=[{'n':3}]:raise AssertionError('Title gateway duplicated immutable decisions')
