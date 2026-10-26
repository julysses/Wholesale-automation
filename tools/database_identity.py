"""Request-local database identity; no cached client can borrow another JWT."""
from contextvars import ContextVar
from dataclasses import dataclass
import os


@dataclass(frozen=True)
class DatabaseIdentity:
    bearer: str


identity: ContextVar[DatabaseIdentity | None] = ContextVar('database_identity', default=None)


def public_database_key():
    return (os.getenv('SUPABASE_PUBLISHABLE_KEY') or os.getenv('SUPABASE_ANON_KEY')
            or os.getenv('VITE_SUPABASE_ANON_KEY') or '')


def database_credentials():
    """Missing request credentials fail closed; they never select service_role."""
    current = identity.get()
    if current is not None:
        return public_database_key(), current.bearer
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('VITE_SUPABASE_ANON_KEY') or ''
    return key, key


class DatabaseIdentityMiddleware:
    """Keep scoped identity across async handlers, threadpool calls and cleanup.

    With acquisition disabled, existing behavior is unchanged. Public inquiry
    endpoints and signed webhook workers retain their explicit server workflow;
    they must continue authenticating/validating before doing privileged work.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or os.getenv('ACQUISITION_ENABLED', '').lower() != 'true':
            return await self.app(scope, receive, send)
        path = scope.get('path', '').rstrip('/')
        method = scope.get('method', 'GET')
        parts = path.strip('/').split('/')
        public_form = (parts[:2] == ['api','forms'] and (
            (len(parts) == 3 and method == 'GET') or
            (len(parts) == 4 and parts[3] == 'submit' and method == 'POST')
        ))
        server_route = (public_form or
            (method == 'GET' and path in {'/api/health','/api/readiness','/api/config'}) or
            (path.startswith('/webhooks/') and path != '/webhooks/launch_control/csv-queue'))
        operational_route = path.startswith(('/api/', '/internal/', '/v1/', '/webhooks/')) or path == '/v1'
        current = None
        if operational_route and not server_route:
            auth_headers = [value for name,value in scope.get('headers', []) if name.lower() == b'authorization']
            raw = auth_headers[0] if len(auth_headers) == 1 else b''
            scheme, _, token = raw.decode('latin1').partition(' ')
            valid = scheme.lower() == 'bearer' and token and len(token) <= 16384 and not any(c.isspace() for c in token)
            current = DatabaseIdentity(token if valid else '')
        marker = identity.set(current)
        try:
            await self.app(scope, receive, send)
        finally:
            identity.reset(marker)
