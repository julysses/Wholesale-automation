from uuid import UUID

import pytest
from pydantic import ValidationError

from schemas.acquisition_review_renewal import ReviewRenewalRequest, ReviewRenewalReceipt


def identity(n):
    return UUID(f'00000000-0000-4000-8000-{n:012d}')


def command(**patch):
    return dict(id=identity(1),expected_version=2,expected_sequence=3,kind='executed_contract',deadline_term=None,
        root_review_id=identity(2),previous_review_id=identity(3),policy_id=identity(4),
        expected_snapshot_sha256='a'*64,expires_at='2026-11-02T09:00:00-06:00',personally_reviewed=True,
        note='  Personally re-reviewed the unchanged original agreement and current evidence.  ')|patch


def receipt(**patch):
    return dict(workspace_id=identity(5),contract_id=identity(6),contract_version=2,kind='executed_contract',deadline_term=None,
        review_id=identity(1),root_review_id=identity(2),previous_review_id=identity(3),sequence=4,duplicate=True,
        review_recorded=True,approval_current=False,execution_authorized=False)|patch


@pytest.mark.parametrize('kind,term', [('executed_contract',None),('title_findings',None),('disposition_findings',None),
    ('deadline_resolution','effective'),('deadline_resolution','inspection_deadline'),('deadline_resolution','closing_deadline')])
def test_exact_historical_confirmation_for_supported_review_chains(kind,term):
    request=ReviewRenewalRequest.model_validate(command(kind=kind,deadline_term=term))
    saved=ReviewRenewalReceipt.model_validate(receipt(kind=kind,deadline_term=term))
    assert saved.confirms(request,workspace_id=identity(5),contract_id=identity(6))
    assert request.note==command()['note']
    assert not saved.confirms(request,workspace_id=identity(7),contract_id=identity(6))
    assert not saved.confirms(request,workspace_id=identity(5),contract_id=identity(7))


@pytest.mark.parametrize('patch',[{'personally_reviewed':False},{'personally_reviewed':'true'}, {'id':identity(2)}, {'id':identity(3)},
    {'expected_sequence':0},{'expected_sequence':True},{'expected_sequence':2147483647},{'expected_version':0},
    {'kind':'signature_release'},{'deadline_term':'closing_deadline'},{'kind':'deadline_resolution'},
    {'expected_snapshot_sha256':'A'*64},{'expected_snapshot_sha256':'a'*63},{'expires_at':12345},
    {'expires_at':'2026-11-02T09:00:00'},{'note':' '*25},{'note':'Reviewed original\x00 with unsafe text.'}])
def test_rejects_ambiguous_renewal_input(patch):
    with pytest.raises(ValidationError):ReviewRenewalRequest.model_validate(command(**patch))


@pytest.mark.parametrize('field',['actor_id','workspace_id','findings','sources','verification_id','policy_snapshot',
    'approval_current','execution_authorized','revoked_at','original_expires_at'])
def test_client_cannot_rewrite_original_facts_or_assert_authority(field):
    with pytest.raises(ValidationError):ReviewRenewalRequest.model_validate(command(**{field:True}))


@pytest.mark.parametrize('patch',[{'contract_version':1},{'review_id':identity(8)},{'root_review_id':identity(8)},
    {'previous_review_id':identity(8)},{'sequence':5},{'kind':'title_findings'},
    {'kind':'deadline_resolution','deadline_term':'closing_deadline'}])
def test_mismatching_receipt_does_not_confirm_the_original_command(patch):
    assert not ReviewRenewalReceipt.model_validate(receipt(**patch)).confirms(
        ReviewRenewalRequest.model_validate(command()),workspace_id=identity(5),contract_id=identity(6))


@pytest.mark.parametrize('patch',[{'review_recorded':False},{'approval_current':True},{'execution_authorized':True},
    {'duplicate':'true'},{'sequence':True},{'review_id':identity(2)},{'deadline_term':'effective'},
    {'policy_snapshot':{'secret':True}}])
def test_receipt_cannot_grant_authority_or_hide_original_identity(patch):
    with pytest.raises(ValidationError):ReviewRenewalReceipt.model_validate(receipt(**patch))


def test_first_renewal_may_follow_root_but_never_reuse_its_id():
    request=ReviewRenewalRequest.model_validate(command(previous_review_id=identity(2)))
    saved=ReviewRenewalReceipt.model_validate(receipt(previous_review_id=identity(2)))
    assert saved.confirms(request,workspace_id=identity(5),contract_id=identity(6))
    with pytest.raises(ValidationError):request.note='A replacement would change the immutable retry command.'
