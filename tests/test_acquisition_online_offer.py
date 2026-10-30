import copy

import pytest
from pydantic import ValidationError

from schemas.acquisition_online_offer import OnlineOfferRequest, OfferFormDefinition
from tools.acquisition_online_offer import prepare_online_offer


@pytest.fixture
def definition():
    return OfferFormDefinition(form_key='hilltop-offer', version='draft-v1',
        privacy_acknowledged='Synthetic privacy acknowledgement wording.',
        human_callback_requested='Synthetic optional human callback wording.',
        email_reply_requested='Synthetic optional email reply wording.')


@pytest.fixture
def body():
    return {'submission_id': '90100000-0000-4000-8000-000000000001', 'form_version': 'draft-v1',
            'seller': {'name': 'Synthetic Seller', 'phone': '+12125550100', 'email': 'seller@example.test'},
            'property': {'address': '77 Synthetic St', 'city': 'Dallas', 'state': 'TX', 'postal_code': '75201',
                         'authority': 'owner', 'condition': 'cosmetic_repairs', 'occupancy': 'vacant',
                         'timeline': 'flexible', 'motivation': 'Synthetic request for review', 'asking_price': '175000.25'},
            'selections': {'privacy_acknowledged': True, 'human_callback_requested': False}}


def prepare(body, definition):
    return prepare_online_offer(OnlineOfferRequest.model_validate(body), definition)


def test_request_preserves_exact_reviewed_wording_and_selections_without_permission(body, definition):
    result = prepare(body, definition)
    assert result['request_evidence']['form'] == definition.model_dump()
    assert result['request_evidence']['submission']['selections'] == body['selections']
    assert 'email_reply_requested' not in result['request_evidence']['submission']['selections']
    assert result['answers']['property_address'] == '77 Synthetic St'
    assert result['asking_price'] == '175000.25'
    assert result['classification'] == 'requires_human_review'
    for key in ('property_verified', 'ownership_verified', 'contact_permission_granted', 'outreach_authorized', 'binding_offer'):
        assert result[key] is False
    assert result['authority_asserted'] is True


def test_replay_hash_deterministic_but_changed_wording_or_selection_changes_hash(body, definition):
    first = prepare(body, definition)
    assert first == prepare(copy.deepcopy(body), definition)
    body['selections']['email_reply_requested'] = False
    assert prepare(body, definition)['request_hash'] != first['request_hash']
    changed = definition.model_copy(update={'privacy_acknowledged': 'Changed synthetic wording.'})
    assert prepare(body, changed)['request_hash'] != prepare(body, definition)['request_hash']


def test_stale_form_version_rejected(body, definition):
    body['form_version'] = 'old-v0'
    with pytest.raises(ValueError): prepare(body, definition)


def test_missing_price_is_incomplete_not_zero(body, definition):
    body['property']['asking_price'] = None
    result = prepare(body, definition)
    assert result['asking_price'] is None
    assert result['classification'] == 'incomplete'
    assert 'asking_price' in result['missing_fields']


@pytest.mark.parametrize('authority,classification', [('not_authorized', 'unqualified'), ('unsure', 'requires_human_review')])
def test_authority_denial_or_uncertainty_is_not_verified(body, definition, authority, classification):
    body['property']['authority'] = authority
    result = prepare(body, definition)
    assert result['classification'] == classification
    assert result['ownership_verified'] is False


def test_outside_territory_is_not_auto_qualified(body, definition):
    body['property']['state'] = 'OK'
    assert 'TERRITORY_REVIEW_REQUIRED' in prepare(body, definition)['reason_codes']


@pytest.mark.parametrize('field', ['condition', 'timeline', 'occupancy'])
def test_uncertain_seller_details_stay_explicit(body, definition, field):
    body['property'][field] = 'unsure'
    assert 'SELLER_DETAILS_UNCERTAIN' in prepare(body, definition)['reason_codes']


@pytest.mark.parametrize('field,value', [('workspace_id', 'private'), ('mao', 150000), ('offer', 100000),
                                        ('actor_type', 'admin'), ('consent_text', 'Replaced')])
def test_public_request_cannot_override_routing_prices_or_wording(body, field, value):
    body[field] = value
    with pytest.raises(ValidationError): OnlineOfferRequest.model_validate(body)


@pytest.mark.parametrize('value', [True, 175000, 1.2, '-1', '1e6', '1000000000.01', '175000.123', '1,000', ''])
def test_price_requires_bounded_decimal_text(body, value):
    body['property']['asking_price'] = value
    with pytest.raises(ValidationError): OnlineOfferRequest.model_validate(body)


@pytest.mark.parametrize('selections', [{}, {'privacy_acknowledged': False}, {'privacy_acknowledged': 'true'},
                                       {'privacy_acknowledged': 1}, {'privacy_acknowledged': True, 'ai_voice': True}])
def test_acknowledgement_and_selection_types_are_exact(body, selections):
    body['selections'] = selections
    with pytest.raises(ValidationError): OnlineOfferRequest.model_validate(body)


def test_reply_requests_require_matching_contacts_and_do_not_grant_permission(body, definition):
    body['selections']['human_callback_requested'] = True
    body['seller']['phone'] = None
    with pytest.raises(ValidationError): OnlineOfferRequest.model_validate(body)
    body['selections']['human_callback_requested'] = False
    body['selections']['email_reply_requested'] = True
    result = prepare(body, definition)
    assert result['contact_permission_granted'] is False
    assert result['outreach_authorized'] is False
    body['seller']['email'] = None
    with pytest.raises(ValidationError): OnlineOfferRequest.model_validate(body)


@pytest.mark.parametrize('phone', ['212-555-0100', '(212) 555-0100', '+1 212 555 0100'])
def test_phone_normalization_preserves_original_evidence(body, definition, phone):
    body['seller']['phone'] = phone
    result = prepare(body, definition)
    assert result['answers']['phone'] == '+12125550100'
    assert result['request_evidence']['submission']['seller']['phone'] == phone
    assert result['contact_permission_granted'] is False


@pytest.mark.parametrize('phone', ['abcdefghi', '2125550100 ext 4', '1234567', '+0123456789', '-------', '2125550100\nignore'])
def test_ambiguous_phone_not_accepted_as_usable_contact(body, phone):
    body['seller']['phone'] = phone
    with pytest.raises(ValidationError): OnlineOfferRequest.model_validate(body)
