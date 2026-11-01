from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from schemas.acquisition_contract_transitions import ContractTransitionRequest
from schemas.acquisition_contracts import ContractEvidence
from tools.acquisition_contract_snapshot import LifecycleDeal, LifecycleTermsVersion, prepare_transition_snapshot
from tools.acquisition_contracts import review_contract_transition

W = UUID('af000000-0000-4000-8000-000000000001')
C = UUID('af000000-0000-4000-8000-000000000002')
NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


def inputs():
    return dict(workspace_id=W, contract_id=C,
        request=ContractTransitionRequest(id=C, expected_version=2, expected_sequence=1,
            expected_status='executed', target_status='title_review', reason='Review the recorded executed agreement.'),
        deal=LifecycleDeal(id=C, workspace_id=W, acquisition_version=2, acquisition_sequence=1,
                           acquisition_status='executed'),
        version=LifecycleTermsVersion(workspace_id=W, deal_id=C, version=2, terms={
            'purchase_price_cents': None, 'earnest_money_cents': 0,
            'assignment_allowed': None, 'assignment_provisions': None,
            'effective': {'precision': 'date', 'calendar_date': '2026-10-30'},
            'inspection_deadline': {'precision': 'unknown'},
            'closing_deadline': {'precision': 'instant', 'instant': '2026-11-30T17:00:00-06:00'},
            'sources': [{'term': term, 'artifact_id': str(C), 'artifact_version': 1,
                         'sha256': 'a' * 64, 'locator': 'Synthetic clause ' + term}
                        for term in ('earnest_money', 'effective', 'closing_deadline')],
            'note': 'Sourced terms for isolated structural testing.'}),
        now=NOW, snapshot_at=NOW, evidence=())


def test_preserves_source_precision_unknowns_and_explicit_zero_without_authority():
    snapshot = prepare_transition_snapshot(**inputs())
    assert snapshot.effective_at is None and snapshot.effective_date.isoformat() == '2026-10-30'
    assert snapshot.inspection_deadline is None and snapshot.inspection_deadline_date is None
    assert snapshot.closing_deadline.utcoffset().total_seconds() == -21600
    assert snapshot.earnest_money_cents == 0 and snapshot.assignment_allowed is None
    assert snapshot.purchase_price_cents is None
    reviewed = review_contract_transition(snapshot)
    assert 'DATE_ONLY_CONTRACT_TERMS_REQUIRE_REVIEW' in reviewed['reason_codes']
    assert 'EVIDENCE_REQUIRED:executed_contract' in reviewed['reason_codes']
    assert reviewed['readiness'] == 'needs_review' and not reviewed['execution_authorized']


def test_projects_exact_sourced_price_without_dollar_conversion():
    args = inputs()
    row = args['version'].model_dump()
    row['terms']['purchase_price_cents'] = 14000029
    row['terms']['sources'] += ({'term': 'purchase_price', 'artifact_id': C,
        'artifact_version': 1, 'sha256': 'a' * 64, 'locator': 'Synthetic purchase clause'},)
    args['version'] = LifecycleTermsVersion.model_validate(row)
    assert prepare_transition_snapshot(**args).purchase_price_cents == 14000029


@pytest.mark.parametrize('field,value', [('workspace_id', C), ('id', W),
    ('acquisition_version', 3), ('acquisition_sequence', 2), ('acquisition_status', 'title_review')])
def test_rejects_foreign_or_changed_canonical_deal(field, value):
    args = inputs()
    args['deal'] = LifecycleDeal.model_validate(args['deal'].model_dump() | {field: value})
    with pytest.raises(ValueError):
        prepare_transition_snapshot(**args)


@pytest.mark.parametrize('field,value', [('workspace_id', C), ('deal_id', W), ('version', 3)])
def test_rejects_foreign_or_different_terms_version(field, value):
    args = inputs()
    args['version'] = LifecycleTermsVersion.model_validate(args['version'].model_dump() | {field: value})
    with pytest.raises(ValueError):
        prepare_transition_snapshot(**args)


def test_initial_draft_has_no_invented_terms():
    args = inputs()
    args['request'] = ContractTransitionRequest(id=C, expected_version=1, expected_sequence=0,
        expected_status='draft', target_status='pending_signature', reason='Request a separate signature release review.')
    args['deal'] = LifecycleDeal(id=C, workspace_id=W, acquisition_version=1,
                                acquisition_sequence=0, acquisition_status='draft')
    args['version'] = LifecycleTermsVersion(workspace_id=W, deal_id=C, version=1, terms=None)
    snapshot = prepare_transition_snapshot(**args)
    assert snapshot.earnest_money_cents is None and snapshot.closing_deadline is None
    assert review_contract_transition(snapshot)['readiness'] == 'needs_review'


@pytest.mark.parametrize('change', [{'terms': None}, {'version': 1}])
def test_rejects_version_terms_shape_corruption(change):
    row = inputs()['version'].model_dump() | change
    with pytest.raises(ValidationError):
        LifecycleTermsVersion.model_validate(row)


def test_rejects_source_relabelled_as_current_terms_version():
    row = inputs()['version'].model_dump()
    row['terms']['sources'][0]['artifact_version'] = 2
    with pytest.raises(ValidationError):
        LifecycleTermsVersion.model_validate(row)


@pytest.mark.parametrize('legacy', ['stage', 'contract_price', 'closing_date', 'buyer_id'])
def test_deal_projection_cannot_silently_take_legacy_authority(legacy):
    row = inputs()['deal'].model_dump() | {legacy: None}
    with pytest.raises(ValidationError):
        LifecycleDeal.model_validate(row)


def evidence(**changes):
    return ContractEvidence.model_validate(dict(id=W, workspace_id=W, contract_id=C,
        contract_version=1, kind='executed_contract', reviewed_by=W,
        recorded_at='2026-10-30T12:00:00Z', expires_at='2026-11-02T12:00:00Z') | changes)


def test_historical_evidence_is_not_relabelled_for_new_terms():
    args = inputs() | {'evidence': (evidence(),)}
    snapshot = prepare_transition_snapshot(**args)
    assert snapshot.evidence[0].contract_version == 1
    assert 'EVIDENCE_REQUIRED:executed_contract' in review_contract_transition(snapshot)['reason_codes']


@pytest.mark.parametrize('items', [(evidence(workspace_id=C),), (evidence(contract_id=W),),
                                 (evidence(), evidence())])
def test_rejects_foreign_and_duplicate_evidence(items):
    with pytest.raises(ValueError):
        prepare_transition_snapshot(**(inputs() | {'evidence': items}))
