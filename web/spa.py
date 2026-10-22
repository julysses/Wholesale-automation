"""Serve React navigation without hiding missing API routes or static files."""
from pathlib import PurePosixPath

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class SPAFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            first = path.split('/', 1)[0]
            if (exc.status_code != 404 or scope['method'] not in {'GET', 'HEAD'}
                    or first in {'api', 'webhooks', 'v1', 'assets'}
                    or any(PurePosixPath(part).suffix for part in path.split('/'))):
                raise
            return await super().get_response('index.html', scope)
