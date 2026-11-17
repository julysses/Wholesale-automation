"""Server-side human verification for the Hilltop and Jays public forms."""

import os

import httpx
from fastapi import HTTPException

SITEVERIFY = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
FORM_HOSTS = {
    "hilltop-home-co": {"hilltophome.co", "www.hilltophome.co"},
    "the-jays-dallas": {"thejaysdallas.com", "www.thejaysdallas.com"},
}
CRM_HOST = "wholesale-automation.vercel.app"


def challenge_required(slug: str) -> bool:
    return slug in FORM_HOSTS and os.getenv("WEBSITE_TURNSTILE_REQUIRED") == "true"


def challenge_site_key(slug: str) -> str:
    if not challenge_required(slug):
        return ""
    site_key = os.getenv("WEBSITE_TURNSTILE_SITE_KEY", "").strip()
    if not site_key:
        raise _unavailable()
    return site_key


def _unavailable() -> HTTPException:
    return HTTPException(503, {"code": "website_challenge_unavailable",
                              "message": "Verification is temporarily unavailable. Please try again."},
                         headers={"Retry-After": "30"})


async def verify_website_challenge(slug: str, token: str | None) -> None:
    if not challenge_required(slug):
        return

    secret = os.getenv("WEBSITE_TURNSTILE_SECRET", "").strip()
    challenge_site_key(slug)
    if not secret:
        raise _unavailable()
    rejected = HTTPException(403, {"code": "website_challenge_required",
                                  "message": "Please complete the verification and try again."})
    if not token or not token.strip():
        raise rejected

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(SITEVERIFY, json={"secret": secret, "response": token})
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError):
        raise _unavailable() from None

    if not isinstance(result, dict):
        raise _unavailable()
    if result.get("success") is not True:
        errors = result.get("error-codes", [])
        if not isinstance(errors, list) or any(
            error in errors for error in ("internal-error", "missing-input-secret", "invalid-input-secret")
        ):
            raise _unavailable()
        raise rejected

    hostname = result.get("hostname")
    if (not isinstance(hostname, str) or hostname.lower() not in FORM_HOSTS[slug] | {CRM_HOST}
            or result.get("action") != slug):
        raise rejected
