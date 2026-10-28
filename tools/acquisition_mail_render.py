"""Prepare inert mail proof content from already-reviewed repository snapshots.

No I/O, approval writes, routing verification, recipient authorization or fulfillment.
Never accept these snapshots as client assertions; load current evidence server-side.
"""
import hashlib
import html
import ipaddress
import json
import re
import unicodedata
from urllib.parse import urlsplit

from schemas.acquisition_mail_render import MailDestinationSnapshot, MailRenderInput, MailTemplateSnapshot

VERSION = 'acquisition-mail-render-v1'
TOKEN = re.compile(r'\{\{(company_name|property_address|tracking_phone|tracking_url)\}\}')


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def safe_text(value: str, *, multiline: bool = False) -> None:
    if not value.strip() or any(unicodedata.category(c).startswith('C') and not (multiline and c == '\n') for c in value):
        raise ValueError('blank or unsupported control characters in mail text')


def validate_destination(destination: MailDestinationSnapshot) -> None:
    safe_text(destination.value)
    if destination.mode == 'phone':
        if not re.fullmatch(r'\+[1-9][0-9]{7,14}', destination.value):
            raise ValueError('tracked phone must be normalized E.164')
        return
    value = destination.value
    # An exact destination, not a redirect/tracking URL assembled from seller input.
    if any(c.isspace() for c in value) or any(c in value for c in '\\{}<>"%?#'):
        raise ValueError('unsafe tracked URL')
    parsed = urlsplit(value)
    hostname = parsed.hostname or ''
    if (parsed.scheme != 'https' or parsed.username is not None or parsed.password is not None
            or parsed.port is not None or parsed.query or parsed.fragment or '%' in parsed.netloc
            or not re.fullmatch(r'[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9]+(?:[a-z0-9-]*[a-z0-9])?)+', hostname)
            or not re.fullmatch(r'[a-z]{2,63}', hostname.rsplit('.', 1)[-1])
            or hostname.endswith(('.localhost', '.local', '.internal', '.test', '.invalid', '.example'))):
        raise ValueError('tracked URL must be an approved public HTTPS destination without query or fragment')
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError('IP address is not a tracked website')


def content_binding(template: MailTemplateSnapshot, destination: MailDestinationSnapshot, company_name: str) -> str:
    """Digest to show/save with a separate authenticated human content review."""
    if (template.workspace_id, template.campaign_id) != (destination.workspace_id, destination.campaign_id):
        raise ValueError('mail content scope mismatch')
    if template.tracking_mode != destination.mode:
        raise ValueError('mail destination mode mismatch')
    safe_text(company_name)
    if any(c in company_name for c in '{}'):
        raise ValueError('company name cannot contain placeholders')
    safe_text(template.body, multiline=True)
    validate_destination(destination)
    required = '{{tracking_phone}}' if destination.mode == 'phone' else '{{tracking_url}}'
    other = '{{tracking_url}}' if destination.mode == 'phone' else '{{tracking_phone}}'
    if required not in template.body or other in template.body or re.search(r'[{}]', TOKEN.sub('', template.body)):
        raise ValueError('mail template placeholders do not match the tracked destination')
    return digest({'renderer_version': VERSION, 'company_name': company_name, 'template': template.model_dump(mode='json'),
                   'destination': destination.model_dump(mode='json')})


def render_mail_proof(request: MailRenderInput) -> dict:
    scope = (request.workspace_id, request.campaign_id)
    if any((row.workspace_id, row.campaign_id) != scope for row in (request.template, request.destination, request.review)):
        raise ValueError('mail proof scope mismatch')
    destination, review = request.destination, request.review
    if destination.revoked or not destination.verified_at <= request.now < destination.expires_at:
        raise ValueError('mail destination verification unavailable or expired')
    if review.status != 'approved' or not review.reviewed_at <= request.now < review.expires_at:
        raise ValueError('mail content review unavailable or expired')
    if review.reviewed_at < destination.verified_at:
        raise ValueError('mail content review predates destination verification')
    binding = content_binding(request.template, destination, request.company_name)
    if review.binding_digest != binding:
        raise ValueError('mail content changed since review')
    safe_text(request.company_name)
    safe_text(request.property_address, multiline=True)
    # Reject substitution-shaped fields rather than recursively interpreting them.
    if any(c in request.company_name + request.property_address for c in '{}'):
        raise ValueError('mail substitution fields cannot contain placeholders')
    fields = {'company_name': request.company_name, 'property_address': request.property_address,
              'tracking_phone': destination.value, 'tracking_url': destination.value}
    text = TOKEN.sub(lambda match: fields[match.group(1)], request.template.body)
    if len(text) > 40000:
        raise ValueError('rendered mail content exceeds proof limit')
    fingerprint = digest({'renderer_version': VERSION, 'workspace_id': str(request.workspace_id),
        'campaign_id': str(request.campaign_id), 'property_id': str(request.property_id),
        'tracking_id': str(request.tracking_id), 'binding_digest': binding,
        'review': review.model_dump(mode='json'), 'company_name': request.company_name,
        'property_address': request.property_address, 'text': text})
    return {'status': 'proof_prepared', 'execution_authorized': False, 'renderer_version': VERSION,
            'workspace_id': str(request.workspace_id), 'campaign_id': str(request.campaign_id),
            'property_id': str(request.property_id), 'tracking_id': str(request.tracking_id),
            'template_id': str(request.template.template_id), 'template_version': request.template.version,
            'format': request.template.format, 'destination_ref': str(destination.id),
            'destination_version': destination.version, 'review_id': str(review.id),
            'binding_digest': binding, 'proof_digest': fingerprint, 'text': text,
            'prepared_at': request.now.isoformat(),
            'content_valid_until': min(review.expires_at, destination.expires_at).isoformat(),
            # Safe inert fragment only. Vendors must not interpret the plain text as HTML.
            'html_fragment': '<pre>' + html.escape(text, quote=True) + '</pre>'}
