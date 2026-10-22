"""Verify and cold-start the generated function, isolated from source dependencies."""
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[2]
output = root / '.vercel/output'
function = output / 'functions/api/index.py.func'
config = json.loads((function / '.vc-config.json').read_text())
assert config['runtime'] == 'python3.12', config['runtime']
assert config['architecture'] == 'x86_64'
assert config['handler'] == 'vc__handler__python.vc_handler'
mapping = config['filePathMap']
for required in ('api/index.py', 'web/app.py', 'web/spa.py',
                 'web/api/buyer_enrollment.py', 'web/api/buyer_twilio_webhooks.py', 'web/api/buyer_manual.py', 'web/api/buyer_analysis.py', 'web/api/buyer_mutations.py'):
    assert required in mapping, required
routes = json.loads((output / 'config.json').read_text())['routes']
assert any(r.get('dest') == '/api/index.py' for r in routes)
assert (output / 'static/index.html').is_file()
assert any((output / 'static/assets').glob('BuyerEnrollment-*.js'))

with tempfile.TemporaryDirectory(prefix='wholesale-vercel-function-') as directory:
    bundle = Path(directory)
    # The Vercel prebuilt layout maps source/vendor files rather than copying them
    # into the function folder. Materialize exactly that map for cold-start proof.
    import shutil
    for destination, origin in mapping.items():
        source = (root / origin).resolve()
        target = (bundle / destination).resolve()
        assert source.is_relative_to(root) and target.is_relative_to(bundle)
        assert source.is_file(), origin
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(function / 'vc__handler__python.py', bundle / 'vc__handler__python.py')
    guard = root / 'scripts/offline-tests'
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': directory,
           'PYTHONPATH': os.pathsep.join([str(guard), str(bundle / '_vendor'), str(bundle)]),
           'PYTHON_DOTENV_DISABLED': '1', 'DATABASE_URL': 'sqlite:///:memory:',
           'PYTHONDONTWRITEBYTECODE': '1'}
    code = '''
from pathlib import Path
from importlib.metadata import distributions,version
import json,sys
from api.index import app
from fastapi.testclient import TestClient
import web.app
assert Path(web.app.__file__).resolve().is_relative_to(Path.cwd())
c=TestClient(app)
assert c.get('/api/health').status_code==200
assert c.get('/api/buyers/leaderboard').status_code==401
assert c.get('/api/buyers/enrollment-program').status_code==401
assert c.post('/api/buyers/import').status_code==401
assert c.get('/api/buyers/analysis/config').status_code==401
assert c.get('/api/buyers/mutations/00000000-0000-4000-8000-000000000001').status_code==401
assert c.post('/api/buyers/manual',json={'request_id':'00000000-0000-4000-8000-000000000001','buyer':{'first_name':'Synthetic','last_name':'Bundle'}}).status_code==401
assert c.get('/api/buyer-enrollment/config').json()=={'available':False,'program':None}
assert version('twilio')=='9.11.2'
assert version('vercel-runtime')=='0.23.3'
rows=sorted((d.metadata['Name'],d.version) for d in distributions(path=[str(Path.cwd()/'_vendor')]))
print(json.dumps({'python':sys.version.split()[0],'dependencies':rows,'result':'passed'}))
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=bundle, env=env,
                            capture_output=True, text=True)
    if result.returncode:
        sys.stderr.write(result.stderr)
        raise RuntimeError('Generated Vercel function failed isolated cold start')
    evidence = json.loads(result.stdout.strip().splitlines()[-1])
    versions = {re.sub(r'[-_.]+', '-', n).lower(): v for n, v in evidence['dependencies']}
    expected = runpy.run_path(str(root / 'scripts/release/check_python_locks.py'))['read_lock'](root / 'api/requirements.txt')
    assert all(versions.get(n) == v for n, v in expected.items()), 'Bundled API versions differ from reviewed lock'
    extras = {n: v for n, v in versions.items() if n not in expected}
    assert all({'pip': '26.2.2', 'vercel-runtime': '0.23.3'}.get(n) == v for n, v in extras.items()), extras
    evidence.update({'function_runtime': config['runtime'], 'architecture': config['architecture'],
                     'mapped_files': len(mapping), 'provider_calls': 0,
                     'frontend_index_sha256': hashlib.sha256((output / 'static/index.html').read_bytes()).hexdigest()})
    Path('logs').mkdir(exist_ok=True)
    Path('logs/vercel-bundle-requirements.txt').write_text(''.join(f'{n}=={v}\n' for n,v in evidence['dependencies']))
    Path('logs/vercel-artifact-smoke.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({k:v for k,v in evidence.items() if k!='dependencies'}, sort_keys=True))
