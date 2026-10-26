import copy
import pytest
from tools.acquisition_costs import campaign_cost_coverage

W='10000000-0000-4000-8000-000000000001'
C='20000000-0000-4000-8000-000000000001'
I='30000000-0000-4000-8000-000000000001'
J='30000000-0000-4000-8000-000000000002'


def row(**changes):
    return dict(id=I,workspace_id=W,campaign_id=C,date='2026-10-24',revision=1,
                reporting_timezone='America/Chicago',currency='USD',amount_minor=12550,
                coverage='complete',observed_at='2026-10-25T06:00:00Z',
                evidence_ref='private-object-reference',evidence_hash='a'*64) | changes


def report(records, **changes):
    return campaign_cost_coverage(**(dict(workspace_id=W,campaign_id=C,start_date='2026-10-24',
        end_date='2026-10-24',reporting_timezone='America/Chicago',currency='USD',as_of='2026-12-01T00:00:00Z',records=records) | changes))


def test_exact_complete_cost_with_provenance_without_denominator_or_authority():
    records=[row()]; original=copy.deepcopy(records); result=report(records)
    assert result['total_cost_minor']=='12550' and result['observed_cost_minor']=='12550'
    assert result['days'][0]['revision_id']==I and result['days'][0]['evidence_hash']=='a'*64
    assert result['status']=='complete' and result['complete_days']==1
    assert result['cost_per_lead_minor'] is None and result['qualified_cost_per_lead_minor'] is None
    assert result['denominator_status']=='NOT_RECONCILED' and not result['execution_authorized']
    assert 'private-object-reference' not in str(result)
    assert records==original


def test_missing_cost_is_unknown_but_documented_zero_is_zero():
    absent=report([]); assert absent['total_cost_minor'] is None and absent['observed_cost_minor'] is None
    assert absent['reason_codes']==['COST_MISSING']
    zero=report([row(amount_minor=0)]); assert zero['total_cost_minor']=='0'


def test_gap_prevents_window_total_without_discarding_observed_cost():
    value=report([row()],end_date='2026-10-25')
    assert value['total_cost_minor'] is None and value['observed_cost_minor']=='12550'
    assert value['requested_days']==2 and value['complete_days']==1
    assert value['days'][1]['amount_minor'] is None


@pytest.mark.parametrize('coverage,amount,observed', [('partial',900,'900'),('withdrawn',None,None)])
def test_latest_incomplete_revision_invalidates_superseded_complete(coverage,amount,observed):
    newer=row(id=J,revision=2,coverage=coverage,amount_minor=amount)
    for records in ([row(),newer],[newer,row()]):
        value=report(records); assert value['total_cost_minor'] is None
        assert value['observed_cost_minor']==observed and value['days'][0]['revision_id']==J


def test_exact_retry_deduplicates_but_conflicting_identity_or_revision_fails():
    assert report([row(),row()])['total_cost_minor']=='12550'
    with pytest.raises(ValueError,match='identity'): report([row(),row(amount_minor=99)])
    with pytest.raises(ValueError,match='revision'): report([row(),row(id=J)])


@pytest.mark.parametrize('patch', [dict(amount_minor=True),dict(amount_minor=1.5),dict(amount_minor='100'),dict(amount_minor=-1),dict(amount_minor=10**15),dict(currency='CAD'),dict(reporting_timezone='UTC'),dict(workspace_id=C),dict(campaign_id=W),dict(date='2026-10-23'),dict(revision=True),dict(revision=0),dict(coverage='unknown'),dict(coverage='withdrawn'),dict(evidence_hash='bad'),dict(evidence_ref=' '),dict(observed_at='2026-10-25'),dict(id='bad')])
def test_invalid_or_mixed_evidence_rejects_entire_projection(patch):
    with pytest.raises(ValueError): report([row(**patch)])


def test_complete_day_uses_account_local_midnight_not_utc_midnight():
    with pytest.raises(ValueError,match='after that local day'): report([row(observed_at='2026-10-25T04:59:59Z')])
    assert report([row(observed_at='2026-10-25T05:00:00Z')])['status']=='complete'
    assert report([row(coverage='partial',observed_at='2026-10-24T12:00:00Z')])['status']=='incomplete'


def test_dst_end_day_requires_next_local_midnight():
    data=row(date='2026-11-01',observed_at='2026-11-02T05:59:59Z')
    with pytest.raises(ValueError): report([data],start_date='2026-11-01',end_date='2026-11-01')
    data['observed_at']='2026-11-02T06:00:00Z'
    assert report([data],start_date='2026-11-01',end_date='2026-11-01')['status']=='complete'


@pytest.mark.parametrize('patch', [dict(currency='JPY'),dict(reporting_timezone='Not/AZone'),dict(start_date='2026-10-25'),dict(start_date='2025-01-01'),dict(start_date='20261024'),dict(workspace_id='bad')])
def test_invalid_requested_window_scope_and_units_rejected(patch):
    with pytest.raises(ValueError): report([],**patch)


def test_high_precision_multi_day_sum_and_partial_amounts_not_rounded():
    a=row(amount_minor=100_000_000_000_000)
    b=row(id=J,date='2026-10-25',amount_minor=99_999_999_999_999,observed_at='2026-10-26T06:00:00Z')
    assert report([a,b],end_date='2026-10-25')['total_cost_minor']=='199999999999999'


def test_bounded_evidence_batch():
    with pytest.raises(ValueError): report([row()]*10001)
    with pytest.raises(ValueError): report(None)


def test_observation_after_cutoff_cannot_enter_historical_report():
    with pytest.raises(ValueError,match='cutoff'):
        report([row()],as_of='2026-10-25T05:59:59Z')
    assert report([row()],as_of='2026-10-25T06:00:00Z')['status']=='complete'
