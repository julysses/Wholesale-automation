"""Deterministic seller assertions for a future guarded online-offer receiver.

No network, canonical identity lookup, CRM write, pricing, contact eligibility or
permission grant. Caller must supply the current server-owned form definition.
"""
import hashlib
import json

from schemas.acquisition_online_offer import OnlineOfferRequest, OfferFormDefinition, normalize_offer_phone
from tools.acquisition_intake import normalize_seller_fields


def prepare_online_offer(request: OnlineOfferRequest, definition: OfferFormDefinition):
    if request.form_version != definition.version:
        raise ValueError('Form changed; review the current wording before submitting')
    prop, seller = request.property, request.seller
    authority = {'owner': 'owner', 'authorized_representative': 'authorized representative',
                 'not_authorized': 'no', 'unsure': 'unsure'}[prop.authority]
    values = {'property_address': prop.address, 'city': prop.city, 'state': prop.state,
              'zip_code': prop.postal_code, 'full_name': seller.name, 'phone': seller.phone,
              'email': seller.email, 'authority': authority, 'condition': prop.condition,
              'occupancy': prop.occupancy, 'timeline': prop.timeline, 'motivation': prop.motivation,
              'asking_price': prop.asking_price}
    normalized = normalize_seller_fields([{'name': key, 'values': [value]} for key, value in values.items() if value is not None])
    if seller.phone:
        normalized['answers']['phone'] = normalize_offer_phone(seller.phone)
    if seller.email:
        normalized['answers']['email'] = seller.email.lower()
    if prop.condition == 'unsure' or prop.timeline == 'unsure' or prop.occupancy == 'unsure':
        normalized['reason_codes'].append('SELLER_DETAILS_UNCERTAIN')
    # Serialize exact validated selections and exact reviewed wording. Neither
    # callback/email requests nor privacy acknowledgement grant contact permission.
    evidence = {'form': definition.model_dump(mode='json'), 'submission': request.model_dump(mode='json')}
    canonical = json.dumps(evidence, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)
    return {'version': 'seller-intake-v1', 'source_type': 'online_offer_portal',
            'submission_id': str(request.submission_id), 'form_key': definition.form_key,
            'form_version': definition.version, 'request_evidence': evidence,
            'request_hash': hashlib.sha256(canonical.encode('utf-8')).hexdigest(),
            **normalized}
