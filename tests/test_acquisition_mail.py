"""Mail selection safety boundaries; no provider, database or fulfillment calls."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from schemas.acquisition_mail import MailBatchInput
from tools.acquisition_mail import prepare_mail_batch

NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
uid = lambda n: UUID(int=n)


def candidate(n=10, **overrides):
    return dict(workspace_id=uid(1), lead_id=uid(n+100), property_id=uid(n), owner_id=uid(n+200),
                score=90, county='Dallas', state='TX', recipient_address_key=f'validated-recipient-unit-{n}',
                address_status='verified', address_evidence_ref=uid(300+n),
                address_expires_at=NOW+timedelta(days=1), owner_status='living', preference='clear',
                eligibility='ALLOW', eligibility_decision_id=uid(400+n),
                eligibility_expires_at=NOW+timedelta(minutes=1)) | overrides


def history(**overrides):
    return dict(workspace_id=uid(1), campaign_id=uid(2), job_id=uid(500), property_id=uid(10),
                recipient_address_key='validated-recipient-unit-10', status='fulfilled',
                effective_at=NOW-timedelta(days=1), cost_cents=75) | overrides


def batch(**overrides):
    data=dict(workspace_id=uid(1), campaign_id=uid(2), batch_id=uid(3), template_id=uid(4),
              template_version=1, format='letter', tracking_destination_ref=uid(5), vendor_id='sandbox-unselected',
              quote_ref=uid(6), currency='USD', quote_expires_at=NOW+timedelta(hours=1), unit_cost_cents=75,
              budget_cents=225, minimum_score=70, frequency_days=30, maximum_pieces=10,
              now=NOW, history_as_of=NOW, history_complete=True,
              candidates=(candidate(),), history=())
    return MailBatchInput.model_validate(data | overrides)


def reasons(result):
    return set(result['held'][0]['reason_codes'])


def test_deterministic_rank_budget_tracking_and_no_authority():
    rows=[candidate(12,score=80),candidate(11,score=95),candidate(10,score=95)]
    result=prepare_mail_batch(batch(candidates=rows,budget_cents=150))
    assert result==prepare_mail_batch(batch(candidates=list(reversed(rows)),budget_cents=150))
    assert [r['property_id'] for r in result['selected']]==[str(uid(10)),str(uid(11))]
    assert result['proposed_cents']==150 and result['remaining_cents']==0
    assert result['held'][0]['reason_codes']==['BUDGET_LIMIT']
    assert len({r['tracking_id'] for r in result['selected']})==2
    assert result['execution_authorized'] is False and result['status']=='proposed'
    assert 'recipient_address_key' not in str(result)


@pytest.mark.parametrize('change,reason',[
    ({'county':'other'},'OUTSIDE_INITIAL_TERRITORY'),
    ({'state':'CA'},'OUTSIDE_INITIAL_TERRITORY'),
    ({'score':None},'SCORE_MISSING_OR_BELOW_MINIMUM'),
    ({'score':69},'SCORE_MISSING_OR_BELOW_MINIMUM'),
    ({'address_status':'undeliverable'},'ADDRESS_NOT_VERIFIED'),
    ({'address_evidence_ref':None},'ADDRESS_NOT_VERIFIED'),
    ({'recipient_address_key':None},'ADDRESS_NOT_VERIFIED'),
    ({'address_expires_at':NOW},'ADDRESS_NOT_VERIFIED'),
    ({'owner_status':'deceased'},'OWNER_REVIEW_REQUIRED'),
    ({'owner_status':'unknown'},'OWNER_REVIEW_REQUIRED'),
    ({'preference':'unknown'},'CONTACT_PREFERENCE_HOLD'),
    ({'preference':'suppressed'},'CONTACT_PREFERENCE_HOLD'),
    ({'eligibility':'REVIEW'},'ELIGIBILITY_NOT_ALLOWED'),
    ({'eligibility':'BLOCK'},'ELIGIBILITY_NOT_ALLOWED'),
    ({'eligibility_expires_at':None},'ELIGIBILITY_NOT_ALLOWED'),
    ({'eligibility_expires_at':NOW},'ELIGIBILITY_NOT_ALLOWED'),
])
def test_candidate_holds(change,reason):
    result=prepare_mail_batch(batch(candidates=[candidate(**change)]))
    assert result['selected']==[] and reason in reasons(result)


@pytest.mark.parametrize('change,reason',[
    ({'history_complete':False},'HISTORY_INCOMPLETE_OR_STALE'),
    ({'history_as_of':NOW-timedelta(minutes=6)},'HISTORY_INCOMPLETE_OR_STALE'),
    ({'quote_expires_at':NOW},'QUOTE_EXPIRED'),
    ({'history':[history(cost_cents=226)]},'BUDGET_ALREADY_EXCEEDED'),
])
def test_batch_holds(change,reason):
    result=prepare_mail_batch(batch(**change))
    assert result['selected']==[] and reason in reasons(result)


def test_dedup_preserves_units_and_collapses_exact_properties():
    first=candidate()
    same_recipient=candidate(11,recipient_address_key=first['recipient_address_key'])
    other_unit=candidate(12)
    result=prepare_mail_batch(batch(candidates=[first,first,same_recipient,other_unit]))
    assert len(result['selected'])==2
    assert result['held'][0]['reason_codes']==['DUPLICATE_RECIPIENT']
    with pytest.raises(ValueError,match='conflicting'):
        prepare_mail_batch(batch(candidates=[first,candidate(score=80)]))


def test_cadence_cross_campaign_property_and_recipient():
    for past in [history(campaign_id=uid(99)),history(property_id=uid(99),campaign_id=uid(99))]:
        result=prepare_mail_batch(batch(history=[past]))
        assert 'FREQUENCY_OR_PENDING_JOB_HOLD' in reasons(result)
        assert result['committed_cents']==0


@pytest.mark.parametrize('status',['approved','submitting','submitted','unknown','failed','cancelled'])
def test_unreconciled_jobs_never_age_out_or_release_budget(status):
    result=prepare_mail_batch(batch(history=[history(status=status,effective_at=NOW-timedelta(days=400))]))
    assert result['selected']==[]
    assert result['committed_cents']==75
    assert 'FREQUENCY_OR_PENDING_JOB_HOLD' in reasons(result)


def test_lifetime_budget_and_cadence_boundary():
    past=history(effective_at=NOW-timedelta(days=30))
    result=prepare_mail_batch(batch(history=[past]))
    assert len(result['selected'])==1 and result['committed_cents']==75
    assert result['remaining_cents']==75
    just_recent=past | {'effective_at':past['effective_at']+timedelta(microseconds=1)}
    assert not prepare_mail_batch(batch(history=[just_recent]))['selected']


@pytest.mark.parametrize('status',['failed','cancelled'])
def test_only_evidenced_nonfulfillment_releases_failed_job(status):
    result=prepare_mail_batch(batch(history=[history(status=status,release_evidence_ref=uid(88))]))
    assert len(result['selected'])==1 and result['committed_cents']==0
    result=prepare_mail_batch(batch(history=[history(status='fulfilled',release_evidence_ref=uid(88))]))
    assert not result['selected'] and result['committed_cents']==75


def test_proposals_are_not_reservations_and_batch_cap_is_enforced():
    result=prepare_mail_batch(batch(history=[history(status='proposed')],
                                    candidates=[candidate(),candidate(11)],maximum_pieces=1))
    assert len(result['selected'])==1 and result['committed_cents']==0
    assert result['held'][0]['reason_codes']==['BATCH_LIMIT']


@pytest.mark.parametrize('changes',[
    {'candidates':[candidate(workspace_id=uid(8))]},
    {'history':[history(workspace_id=uid(8))]},
    {'history':[history(),history()]},
    {'history':[history(effective_at=NOW+timedelta(seconds=1))]},
    {'history_as_of':NOW+timedelta(seconds=1)},
])
def test_bad_repository_snapshots_rejected(changes):
    with pytest.raises(ValueError): prepare_mail_batch(batch(**changes))


@pytest.mark.parametrize('changes',[
    {'unit_cost_cents':True},{'unit_cost_cents':1.5},{'unit_cost_cents':0},
    {'budget_cents':-1},{'frequency_days':0},{'maximum_pieces':False},
    {'now':NOW.replace(tzinfo=None)},{'quote_expires_at':NOW.replace(tzinfo=None)},
    {'history_complete':'true'},{'extra_permission':'ALLOW'},{'currency':'EUR'},
])
def test_invalid_inputs_rejected(changes):
    with pytest.raises(ValidationError): batch(**changes)


def test_changed_template_or_quote_requires_different_snapshot_identity():
    result=prepare_mail_batch(batch())
    assert len(result['snapshot_sha256'])==64
    assert result['snapshot_sha256']!=prepare_mail_batch(batch(template_version=2))['snapshot_sha256']
    assert result['snapshot_sha256']!=prepare_mail_batch(batch(quote_ref=uid(99)))['snapshot_sha256']


def test_held_candidate_does_not_consume_budget_or_duplicate_slot():
    result=prepare_mail_batch(batch(budget_cents=75,candidates=[
        candidate(10,score=99,preference='suppressed'),
        candidate(11,recipient_address_key='validated-recipient-unit-10')]))
    assert [row['property_id'] for row in result['selected']]==[str(uid(11))]
    assert result['proposed_cents']==75


def test_incomplete_or_stale_history_does_not_claim_available_budget():
    for changes in ({'history_complete':False}, {'history_as_of':NOW-timedelta(minutes=6)}):
        result=prepare_mail_batch(batch(**changes))
        assert result['committed_cents'] is None
        assert result['remaining_cents'] is None
        assert result['proposed_cents']==0
