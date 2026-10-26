"""Cutover fence for legacy transports that lack fresh acquisition authorization.

The pending acquisition policy cannot issue ALLOW. Do not add a caller-supplied
boolean, cached decision, or environment override to bypass this fence. A future
acquisition executor must consume a fresh, scoped database authorization and
preserve provider idempotency before replacing these legacy paths.
"""
import os

HOLD_REASON = 'acquisition_execution_not_authorized'


class AcquisitionExecutionRequired(RuntimeError):
    pass


def legacy_transport_held() -> bool:
    # Match the existing acquisition API/database-identity mode exactly; inspect
    # per invocation so a preconstructed provider client cannot cache permission.
    return os.getenv('ACQUISITION_ENABLED', '').lower() == 'true'


def require_legacy_transport_allowed() -> None:
    if legacy_transport_held():
        raise AcquisitionExecutionRequired(HOLD_REASON)
