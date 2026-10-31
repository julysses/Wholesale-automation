"""Contract review boundaries; no persistence, legal determination or execution."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from schemas.acquisition_contracts import ContractReviewSnapshot
from tools.acquisition_contracts import review_contract_transition, NEXT

NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
uid = lambda n: UUID(int=n)


def snapshot(**changes):
    return ContractReviewSnapshot.model_validate(dict(
        workspace_id=uid(1), contract_id=uid(2), contract_version=2,
        status='executed', target_status='title_review', now=NOW, snapshot_at=NOW,
        effective_at=NOW-timedelta(days=1), inspection_deadline=NOW+timedelta(days=3),
        closing_deadline=NOW+timedelta(days=20), earnest_money_cents=0,
        evidence=[evidence('executed_contract')]) | changes)


def evidence(kind, n=10, **changes):
    return dict(id=uid(n), workspace_id=uid(1), contract_id=uid(2), contract_version=2,
                kind=kind, reviewed_by=uid(3), recorded_at=NOW-timedelta(hours=1),
                expires_at=NOW+timedelta(days=1)) | changes


def test_review_entry_preserves_unknowns_and_never_authorizes():
    result=review_contract_transition(snapshot())
    assert result['readiness']=='ready_for_review'
    assert result['execution_authorized'] is False
    assert 'reviewed_by' not in str(result)
    assert 'CONTRACT_TERMS_INCOMPLETE' in review_contract_transition(snapshot(earnest_money_cents=None))['reason_codes']


@pytest.mark.parametrize('field,value',[
    ('revoked',True),('contract_version',1),('expires_at',NOW),
    ('recorded_at',NOW+timedelta(minutes=1)),
])
def test_old_revoked_expired_future_evidence_is_not_current(field,value):
    result=review_contract_transition(snapshot(evidence=[evidence('executed_contract',**{field:value})]))
    assert 'EVIDENCE_REQUIRED:executed_contract' in result['reason_codes']


@pytest.mark.parametrize('field,value',[('workspace_id',uid(9)),('contract_id',uid(9))])
def test_scope_mismatch_fails(field,value):
    with pytest.raises(ValueError,match='scope mismatch'):
        review_contract_transition(snapshot(evidence=[evidence('executed_contract',**{field:value})]))


def test_duplicate_evidence_rejected():
    with pytest.raises(ValueError,match='Duplicate'):
        review_contract_transition(snapshot(evidence=[evidence('executed_contract')]*2))


@pytest.mark.parametrize('status',['closed','cancelled','expired'])
@pytest.mark.parametrize('target',list(NEXT))
def test_terminal_contracts_cannot_reopen(status,target):
    assert 'TRANSITION_NOT_PERMITTED' in review_contract_transition(snapshot(status=status,target_status=target))['reason_codes']


def test_cannot_skip_reviews_or_resolve_dispute_without_evidence():
    assert 'TRANSITION_NOT_PERMITTED' in review_contract_transition(snapshot(status='draft',target_status='closed'))['reason_codes']
    assert 'EVIDENCE_REQUIRED:dispute_resolution' in review_contract_transition(snapshot(status='disputed'))['reason_codes']


@pytest.mark.parametrize('target,kind',[('cancelled','cancellation_review'),('expired','expiration_review'),('disputed','dispute_report')])
def test_exception_paths_require_evidence_even_after_deadline(target,kind):
    result=review_contract_transition(snapshot(target_status=target,closing_deadline=NOW-timedelta(hours=1)))
    assert result['reason_codes']==['EVIDENCE_REQUIRED:'+kind]
    assert review_contract_transition(snapshot(target_status=target,evidence=[evidence(kind)]))['readiness']=='ready_for_review'


def test_disposition_review_precedes_buyer_selection():
    proofs=[evidence(kind,n,exit_type='wholesale_assignment' if kind=='assignment_basis' else None) for n,kind in enumerate(['executed_contract','contract_review','title_review','assignment_basis'],10)]
    result=review_contract_transition(snapshot(status='title_review',target_status='disposition_review',
        exit_type='wholesale_assignment',assignment_allowed=True,evidence=proofs))
    assert result['readiness']=='ready_for_review'
    assert result['execution_authorized'] is False
    assert 'ASSIGNMENT_NOT_CONFIRMED' in review_contract_transition(snapshot(status='title_review',target_status='disposition_review',exit_type='wholesale_assignment',evidence=proofs))['reason_codes']


def assignment(**changes):
    kinds=['executed_contract','contract_review','title_review','assignment_basis','seller_disclosure',
           'assignee_disclosure','buyer_verification','structure_approval','assignment_agreement','deposit_confirmation']
    proofs=[evidence(kind,n,buyer_id=uid(50),exit_type='wholesale_assignment') for n,kind in enumerate(kinds,10)]
    return snapshot(**(dict(status='disposition_review',target_status='assigned_or_direct_close',
        exit_type='wholesale_assignment',assignment_allowed=True,buyer_id=uid(50),evidence=proofs)|changes))


def test_assignment_requires_exact_buyer_and_current_structure_approval():
    assert review_contract_transition(assignment())['readiness']=='ready_for_review'
    changed=review_contract_transition(assignment(buyer_id=uid(51)))
    assert 'EVIDENCE_REQUIRED:structure_approval' in changed['reason_codes']
    assert 'EVIDENCE_REQUIRED:assignee_disclosure' in changed['reason_codes']
    assert 'EVIDENCE_REQUIRED:assignment_agreement' in changed['reason_codes']
    assert 'BUYER_REQUIRED' in review_contract_transition(assignment(buyer_id=None))['reason_codes']


def test_direct_close_has_separate_requirements_and_closing_confirmation():
    kinds=['executed_contract','contract_review','title_review','structure_approval']
    proofs=[evidence(kind,n,exit_type='principal_acquisition') for n,kind in enumerate(kinds,10)]
    s=snapshot(status='disposition_review',target_status='assigned_or_direct_close',exit_type='principal_acquisition',evidence=proofs)
    assert review_contract_transition(s)['readiness']=='ready_for_review'
    closed=s.model_copy(update={'status':'assigned_or_direct_close','target_status':'closed'})
    assert review_contract_transition(closed)['reason_codes']==['EVIDENCE_REQUIRED:closing_confirmation']
    proofs.append(evidence('closing_confirmation',30,exit_type='principal_acquisition'))
    result=review_contract_transition(snapshot(status='assigned_or_direct_close',target_status='closed',exit_type='principal_acquisition',evidence=proofs))
    assert result['readiness']=='ready_for_review' and result['execution_authorized'] is False


@pytest.mark.parametrize('change,reason',[
    ({'snapshot_at':NOW-timedelta(minutes=6)},'SNAPSHOT_NOT_CURRENT'),
    ({'snapshot_at':NOW+timedelta(seconds=1)},'SNAPSHOT_NOT_CURRENT'),
    ({'closing_deadline':NOW},'CLOSING_DEADLINE_PASSED'),
    ({'inspection_deadline':NOW+timedelta(days=21)},'CONTRACT_DEADLINES_REQUIRE_REVIEW'),
])
def test_stale_snapshot_and_deadlines_hold_progress(change,reason):
    assert reason in review_contract_transition(snapshot(**change))['reason_codes']


@pytest.mark.parametrize('change',[{'contract_version':True},{'earnest_money_cents':False},{'now':NOW.replace(tzinfo=None)},{'assignment_allowed':'true'},{'permission_override':True}])
def test_invalid_assertion_shape_rejected(change):
    with pytest.raises(ValidationError):
        snapshot(**change)


def test_principal_review_is_not_assignment_basis():
    s=assignment()
    proofs=tuple(e.model_copy(update={'exit_type':'principal_acquisition'}) if e.kind=='assignment_basis' else e for e in s.evidence)
    result=review_contract_transition(s.model_copy(update={'evidence':proofs}))
    assert 'EVIDENCE_REQUIRED:assignment_basis' in result['reason_codes']


@pytest.mark.parametrize('instant,calendar', [('effective_at','effective_date'),
    ('inspection_deadline','inspection_deadline_date'),('closing_deadline','closing_deadline_date')])
def test_date_only_source_stays_date_only_and_holds_forward_review(instant,calendar):
    s=snapshot(**{instant:None,calendar:'2026-11-01'})
    assert getattr(s,instant) is None and getattr(s,calendar).isoformat()=='2026-11-01'
    result=review_contract_transition(s)
    assert result['readiness']=='needs_review' and result['execution_authorized'] is False
    assert 'DATE_ONLY_CONTRACT_TERMS_REQUIRE_REVIEW' in result['reason_codes']
    assert 'CLOSING_DEADLINE_PASSED' not in result['reason_codes']
    assert 'date' in result['term_precision'].values()
    with pytest.raises(ValidationError,match='both date-only and instant'):
        snapshot(**{calendar:'2026-11-01'})


@pytest.mark.parametrize('value',[NOW, '2026-11-01T00:00:00Z', '20261101', 1793491200, True])
def test_date_only_source_rejects_silent_precision_coercion(value):
    with pytest.raises(ValidationError):
        snapshot(closing_deadline=None,closing_deadline_date=value)


def test_unknown_date_precision_and_exception_review_do_not_invent_expiration():
    s=snapshot(closing_deadline=None,closing_deadline_date='2020-01-01',target_status='expired',evidence=[evidence('expiration_review')])
    result=review_contract_transition(s)
    assert result['readiness']=='ready_for_review' and result['execution_authorized'] is False
    assert result['term_precision']['closing_deadline']=='date'
    result=review_contract_transition(snapshot(closing_deadline=None))
    assert result['term_precision']['closing_deadline']=='unknown'
    assert 'CONTRACT_TERMS_INCOMPLETE' in result['reason_codes']
