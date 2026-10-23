"""Execute inside the built image with --network none and no injected secrets."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from importlib.metadata import version


def get(path):
    try:
        with urlopen('http://127.0.0.1:8000' + path, timeout=2) as response:
            return response.status, response.headers, response.read()
    except HTTPError as exc:
        return exc.code, exc.headers, exc.read()


assert os.getuid() != 0, 'Release must run without root'
for key in ('SUPABASE_SERVICE_ROLE_KEY', 'TWILIO_AUTH_TOKEN', 'SENDGRID_API_KEY',
            'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'SUPABASE_URL'):
    assert not os.environ.get(key), f'Smoke check must not receive {key}'
for key in ('SMS_LIVE_ENABLED', 'BUYER_SMS_LIVE_ENABLED', 'EMAIL_LIVE_ENABLED',
            'AI_CALLING_LIVE_ENABLED', 'SMS_NURTURE_ENABLED', 'BUYER_ENROLLMENT_ENABLED'):
    assert os.environ.get(key, 'false').lower() == 'false', key

server = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'web.app:app',
                           '--host', '127.0.0.1', '--port', '8000'])
try:
    deadline = time.monotonic() + 40
    while True:
        assert server.poll() is None, 'Release server exited during cold start'
        try:
            status, _, body = get('/api/health')
            assert status == 200 and json.loads(body)['status'] == 'ok'
            break
        except URLError:
            if time.monotonic() >= deadline:
                raise TimeoutError('Release health did not become ready')
            time.sleep(.25)
    index = Path('frontend/dist/index.html').read_bytes()
    for path in ('/', '/buyers', '/buyer-sms', '/buyer-sms/privacy', '/buyer-sms/terms'):
        status, headers, body = get(path)
        assert status == 200 and body == index and 'text/html' in headers['Content-Type'], path
    for path in ('/api/buyers/leaderboard', '/api/buyers/enrollment-program'):
        assert get(path)[0] == 401, path
    status, _, body = get('/api/buyer-enrollment/config')
    assert status == 200 and json.loads(body) == {'available': False, 'program': None}
    for path in ('/assets/missing.js', '/api/missing', '/webhooks/missing'):
        assert get(path)[0] == 404, path
    assets = sorted(Path('frontend/dist/assets').glob('*'))
    assert assets, 'Frontend assets missing from image'
    for asset in assets:
        status, _, body = get('/assets/' + asset.name)
        assert status == 200 and hashlib.sha256(body).digest() == hashlib.sha256(asset.read_bytes()).digest()
    print(json.dumps({'result': 'passed', 'platform': platform.platform(),
          'python': platform.python_version(), 'uid': os.getuid(),
          'pip': version('pip'), 'twilio': version('twilio'),
          'frontend_index_sha256': hashlib.sha256(index).hexdigest(),
          'asset_count': len(assets), 'external_network': 'disabled by docker --network none',
          'production_credentials': False, 'provider_calls': 0}, sort_keys=True))
finally:
    server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait()
