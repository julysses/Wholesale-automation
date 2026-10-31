"""Public request-for-review transport, closed until explicit deployment approval."""
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from schemas.acquisition_online_offer import OfferFormDefinition
from tools.acquisition_portal_admission import admit_portal_request, portal_network_hash
from tools.acquisition_portal_runtime import configured_portal, open_portal_store
from tools.acquisition_portal_submission import submit_portal_inquiry
from tools.acquisition_portal_transport import read_portal_envelope

router = APIRouter(prefix='/api/acquisition/portal', tags=['Acquisition seller portal'])


def _context(request, form_key):
    config = configured_portal()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}', form_key) or request.url.query:
        raise HTTPException(404, 'Offer request form is unavailable')
    # No forwarded header is trusted here. TRANSPORT_APPROVED requires deployment
    # verification that the ASGI client reflects the actual client under the
    # hosting server's explicit proxy allowlist, not arbitrary forwarded input.
    try:
        network = portal_network_hash(request.client.host if request.client else '', config.network_key)
    except ValueError:
        raise HTTPException(503, 'Offer request connection is unavailable') from None
    origins = request.headers.getlist('origin')
    if origins and origins != ['https://'+config.bot.hostname]:
        raise HTTPException(403, 'Offer request origin is not allowed')
    return config, network


def _response(data, status=200, headers=None):
    return JSONResponse(data, status_code=status, headers={**(headers or {}), 'Cache-Control': 'no-store'})


def _failure(error):
    return _response({'detail': error.detail}, error.status_code, error.headers)


@router.get('/{form_key}')
async def display_form(form_key: str, request: Request):
    try:
        config, network = _context(request, form_key)
        async with open_portal_store(config) as store:
            await admit_portal_request(store, form_key=form_key, network_hash=network, purpose='display')
            raw = await store.request('POST', 'rpc/read_acquisition_public_form', body={'p_form_key': form_key})
            try:
                definition = OfferFormDefinition.model_validate(raw)
                if definition.form_key != form_key:
                    raise ValueError('Wrong form')
            except (ValueError, TypeError):
                raise HTTPException(503, 'Offer request form is temporarily unavailable') from None
            return _response({'definition': definition.model_dump(mode='json'), 'bot_site_key': config.site_key})
    except HTTPException as error:
        return _failure(error)


@router.post('/{form_key}')
async def receive_inquiry(form_key: str, request: Request):
    try:
        config, network = _context(request, form_key)
        body = await read_portal_envelope(request)
        async with open_portal_store(config) as store:
            receipt = await submit_portal_inquiry(store, config.bot, form_key=form_key, inquiry=body.inquiry,
                                                  network_hash=network, bot_token=body.bot_token)
        return _response(receipt.model_dump(mode='json'))
    except HTTPException as error:
        return _failure(error)
