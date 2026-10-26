import copy
import json
import pytest
from tools.acquisition_attribution import facebook_attribution
from tools.acquisition_intake import prepare_facebook_intake


def prepared(**overrides):
    data = dict(id='1', form_id='2', campaign_id='3', adset_id='4', ad_id='5',
                created_time='2026-10-26T08:00:00-05:00', is_organic=False, platform='fb',
                field_data=[{'name':'phone','values':['2145550101']}])
    data.update(overrides)
    return prepare_facebook_intake(leadgen_id='1', provider_data=data)


def test_exact_metadata_is_projected_without_private_answers_or_implied_spend():
    source = prepared(); original = copy.deepcopy(source)
    value = facebook_attribution(source)
    assert value['status'] == 'available'
    assert value['campaign_id'] == '3' and value['adset_id'] == '4' and value['ad_id'] == '5'
    assert value['submitted_at'] == '2026-10-26T13:00:00+00:00'
    assert value['is_organic'] is False
    assert value['spend_cents'] is None and value['internal_campaign_id'] is None
    assert '2145550101' not in json.dumps(value)
    assert source == original


def test_missing_metadata_stays_unknown_and_organic_does_not_imply_zero_cost():
    value = facebook_attribution(prepared(campaign_id=None, adset_id=None, ad_id=None, is_organic=True))
    assert value['status'] == 'partial' and value['campaign_id'] is None
    assert value['missing_fields'] == ['campaign_id','adset_id','ad_id']
    assert value['spend_cents'] is None


@pytest.mark.parametrize('key,value,reason', [('campaign_id',123,'INVALID_CAMPAIGN_ID'),('ad_id',True,'INVALID_AD_ID'),
    ('adset_id',['4'],'INVALID_ADSET_ID'),('created_time','2026-10-26','INVALID_SUBMITTED_AT'),
    ('is_organic','false','INVALID_IS_ORGANIC'),('platform','<private payload>','INVALID_PLATFORM')])
def test_malformed_metadata_is_reviewable_without_coercion(key,value,reason):
    result = facebook_attribution(prepared(**{key:value}))
    assert result['status'] == 'requires_review' and reason in result['reason_codes']


def test_modified_or_missing_evidence_is_not_trusted():
    source = prepared(); source['provider_evidence']['campaign_id']='999'
    value = facebook_attribution(source)
    assert value['reason_codes'] == ['PROVIDER_EVIDENCE_UNVERIFIED'] and value['campaign_id'] is None
    source.pop('provider_evidence_hash')
    assert facebook_attribution(source)['evidence_hash'] is None


def test_identity_disagreement_is_explicit():
    source = prepared(); source['external_lead_id']='other'
    assert 'INTAKE_IDENTITY_MISMATCH' in facebook_attribution(source)['reason_codes']
