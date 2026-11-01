"""Untrusted lifecycle commands cannot supply authority or clear another request."""
from uuid import UUID

import pytest
from pydantic import ValidationError

from schemas.acquisition_contract_transitions import ContractTransitionReceipt, ContractTransitionRequest

WORKSPACE = UUID('af000000-0000-4000-8000-000000000001')
CONTRACT = UUID('af000000-0000-4000-8000-000000000002')
REQUEST = UUID('af000000-0000-4000-8000-000000000003')


def command(**changes):
    return dict(id=str(REQUEST), expected_version=4, expected_sequence=2,
                expected_status='executed', target_status='title_review',
                reason='  Request title review of the recorded executed contract.  ') | changes


def receipt(**changes):
    return dict(workspace_id=WORKSPACE, contract_id=CONTRACT, request_id=REQUEST,
                contract_version=4, sequence=3, previous_status='executed',
                recorded_status='title_review', duplicate=False,
                transition_recorded=True, execution_authorized=False) | changes


@pytest.mark.parametrize('extra', ['workspace_id', 'actor_id', 'policy_id', 'evidence',
                                  'personally_reviewed', 'execution_authorized',
                                  'assignment_allowed', 'buyer_id', 'exit_type', 'now'])
def test_client_cannot_assert_scope_evidence_or_authority(extra):
    with pytest.raises(ValidationError):
        ContractTransitionRequest.model_validate(command(**{extra: True}))


@pytest.mark.parametrize('change', [
    {'expected_version': True}, {'expected_version': '4'}, {'expected_version': 0},
    {'expected_sequence': 2.0}, {'expected_sequence': -1}, {'expected_sequence': 2147483647},
    {'reason': ' ' * 40}, {'reason': 'A long enough reason with a NUL\x00'},
    {'expected_status': 'draft', 'target_status': 'executed'},
    {'expected_status': 'closed'}, {'expected_status': 'cancelled'},
    {'expected_status': 'expired'}, {'target_status': 'executed'},
    {'expected_status': 'disputed', 'target_status': 'closed'},
])
def test_rejects_coercion_terminal_changes_skips_and_empty_reasons(change):
    with pytest.raises(ValidationError):
        ContractTransitionRequest.model_validate(command(**change))


def test_terms_version_is_independent_of_lifecycle_sequence_and_reason_is_exact():
    request = ContractTransitionRequest.model_validate(command(expected_version=9, expected_sequence=0))
    assert request.expected_version == 9 and request.expected_sequence == 0
    assert request.reason == command()['reason']
    assert ContractTransitionRequest.model_validate_json(request.model_dump_json()) == request


@pytest.mark.parametrize('status,target', [('draft', 'pending_signature'), ('draft', 'cancelled'),
    ('pending_signature', 'executed'), ('executed', 'title_review'),
    ('title_review', 'disposition_review'), ('disposition_review', 'assigned_or_direct_close'),
    ('assigned_or_direct_close', 'closed'), ('disputed', 'title_review'),
    ('disputed', 'cancelled'), ('disputed', 'expired')])
def test_structurally_permitted_requests_make_no_authority_claim(status, target):
    request = ContractTransitionRequest.model_validate(command(expected_status=status, target_status=target))
    assert 'execution_authorized' not in request.model_dump()


@pytest.mark.parametrize('duplicate', [False, True])
def test_original_and_retry_receipts_confirm_exact_request_only(duplicate):
    request = ContractTransitionRequest.model_validate(command())
    result = ContractTransitionReceipt.model_validate(receipt(duplicate=duplicate))
    assert result.confirms(request, workspace_id=WORKSPACE, contract_id=CONTRACT)
    for changed in [command(id=str(WORKSPACE)), command(expected_version=5),
                    command(expected_sequence=3), command(target_status='cancelled'),
                    command(expected_status='disputed')]:
        assert not result.confirms(ContractTransitionRequest.model_validate(changed),
                                   workspace_id=WORKSPACE, contract_id=CONTRACT)
    assert not result.confirms(request, workspace_id=CONTRACT, contract_id=CONTRACT)
    assert not result.confirms(request, workspace_id=WORKSPACE, contract_id=WORKSPACE)


@pytest.mark.parametrize('change', [{'execution_authorized': True}, {'execution_authorized': 'false'},
    {'transition_recorded': False}, {'duplicate': 1}, {'sequence': 0},
    {'previous_status': 'closed'}, {'recorded_status': 'executed'}, {'approval_current': True}])
def test_receipts_cannot_grant_authority_or_claim_unrecorded_transitions(change):
    with pytest.raises(ValidationError):
        ContractTransitionReceipt.model_validate(receipt(**change))
