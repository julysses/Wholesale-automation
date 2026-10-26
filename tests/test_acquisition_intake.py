"""Seller-intake normalization preserves ambiguity; no provider or database calls."""
import pytest
from tools.acquisition_intake import prepare_facebook_intake


def payload(**overrides):
    answers = dict(property_address='123 Main St', city='Dallas', state='TX',
                   authority='yes', condition='needs repairs', timeline='30 days',
                   motivation='inherited home', asking_price='$150,000.00', phone='+12145550101')
    answers.update(overrides)
    return {'id': 'native-1', 'form_id': 'form-1', 'created_time': '2026-10-26T12:00:00Z',
            'field_data': [{'name': k, 'values': [v]} for k, v in answers.items()]}


def prepare(data):
    return prepare_facebook_intake(leadgen_id='native-1', provider_data=data)


def test_complete_seller_answers_require_verified_canonical_property():
    result = prepare(payload())
    assert result['asking_price'] == '150000.00'
    assert result['authority_asserted'] is True
    assert result['classification'] == 'requires_human_review'
    assert result['reason_codes'] == ['CANONICAL_PROPERTY_REVIEW_REQUIRED']
    assert not result['property_verified'] and not result['ownership_verified']
    assert result['provider_form_id'] == 'form-1'


def test_missing_price_does_not_become_zero_and_missing_address_is_incomplete():
    result = prepare(payload(asking_price='', property_address=''))
    assert result['asking_price'] is None
    assert result['classification'] == 'incomplete'
    assert result['missing_fields'] == ['property_address', 'asking_price']


@pytest.mark.parametrize('value', ['$0', '0.00', '0'])
def test_explicit_zero_preserved(value):
    assert prepare(payload(asking_price=value))['asking_price'] == '0.00'


@pytest.mark.parametrize('value', ['150k', '150-175000', '1,50,000', '-1', 'NaN', '150.001', '150.000,00'])
def test_ambiguous_prices_remain_unknown(value):
    result = prepare(payload(asking_price=value))
    assert result['asking_price'] is None
    assert result['ambiguous_fields'] == ['asking_price']
    assert result['classification'] == 'requires_human_review'


def test_alias_and_multiselect_conflicts_do_not_overwrite_answers():
    data = payload()
    data['field_data'].extend([{'name': 'price', 'values': ['100000']},
                              {'name': 'authority', 'values': ['yes', 'no']}])
    result = prepare(data)
    assert result['conflicting_fields'] == ['asking_price', 'authority']
    assert result['asking_price'] is None and result['authority_asserted'] is None
    assert len(result['field_evidence']) == len(data['field_data'])


def test_identical_duplicate_answers_are_stable():
    data = payload()
    data['field_data'].append({'name': 'street_address', 'values': ['123 Main St', '123 Main St']})
    assert prepare(data)['conflicting_fields'] == []


@pytest.mark.parametrize('overrides', [{'authority': 'no'}, {'interested': 'no'}])
def test_explicit_disqualification(overrides):
    assert prepare(payload(**overrides))['classification'] == 'unqualified'


def test_generic_consent_never_authorizes_contact_or_offer():
    data = payload(sms_opt_in='yes', ai_voice_consent='yes', approved='true')
    result = prepare(data)
    assert not any(result[key] for key in ('contact_permission_granted', 'outreach_authorized', 'binding_offer'))
    assert 'sms_opt_in' not in result['answers']
    assert any(item['name'] == 'sms_opt_in' for item in result['field_evidence'])


@pytest.mark.parametrize('data', [None, {}, {'id': 'wrong', 'field_data': []},
    {'id': 'native-1', 'field_data': None}, {'id': 'native-1', 'field_data': [None]},
    {'id': 'native-1', 'field_data': [{'name': 'price', 'values': [100]}]}])
def test_bad_provider_response_rejected(data):
    with pytest.raises(ValueError): prepare(data)
