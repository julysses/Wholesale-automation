"""Reject unpinned/unhashed release dependencies and divergent shared API versions."""
from pathlib import Path
import json
import re
import tomllib

ROOT = Path(__file__).resolve().parents[2]


def read_lock(path):
    records = {}
    declaration = ''
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        declaration += ' ' + line.removesuffix('\\').strip()
        if line.endswith('\\'):
            continue
        match = re.fullmatch(r'\s*([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([^\s;]+)(?:\s+--hash=sha256:[0-9a-f]{64})+\s*', declaration)
        if not match:
            raise ValueError(f'{path.name}: dependency must have one exact version and SHA256 hashes')
        name = re.sub(r'[-_.]+', '-', match[1]).lower()
        if name in records:
            raise ValueError(f'{path.name}: duplicate dependency {name}')
        records[name] = match[2]
        declaration = ''
    if declaration or not records:
        raise ValueError(f'{path.name}: empty or unfinished lock')
    return records


def verify():
    root = read_lock(ROOT / 'requirements.txt')
    api = read_lock(ROOT / 'api/requirements.txt')
    security = read_lock(ROOT / 'requirements-security.txt')
    if read_lock(ROOT / 'requirements-vercel-build.txt') != {'uv': '0.13.5'}:
        raise ValueError('Review and audit the Vercel build installer before changing it')
    for name, version in api.items():
        if root.get(name) != version:
            raise ValueError(f'API dependency diverges from root lock: {name}')
    if (ROOT / '.python-version').read_text().strip() != '3.12':
        raise ValueError('Review runtime and lock targets together before changing Python')
    if (ROOT / 'api/.python-version').read_text().strip() != '3.12':
        raise ValueError('Vercel API package needs its own Python 3.12 selector')
    manifest = tomllib.loads((ROOT / 'api/pyproject.toml').read_text())
    expected = sorted(f'{name}=={version}' for name, version in api.items())
    if sorted(manifest['project']['dependencies']) != expected:
        raise ValueError('Vercel manifest must exactly match the API requirements')
    if manifest['project']['requires-python'] != '>=3.12,<3.13':
        raise ValueError('Vercel API manifest must target Python 3.12')
    if manifest['tool']['uv'].get('environments') != ["sys_platform == 'linux' and platform_machine == 'x86_64'"]:
        raise ValueError('Review the Vercel Linux x86_64 target before changing lock platforms')
    native = tomllib.loads((ROOT / 'api/uv.lock').read_text())
    if native['requires-python'] != '==3.12.*':
        raise ValueError('Native API lock must target Python 3.12')
    local = [p for p in native['package'] if 'registry' not in p['source']]
    if len(local) != 1 or local[0]['name'] != 'wholesaleos-api' or local[0]['source'] != {'virtual': '.'}:
        raise ValueError('Native API lock contains an unreviewed package source')
    registry = [p for p in native['package'] if 'registry' in p['source']]
    if {p['name']: p['version'] for p in registry} != api or len(registry) != len(api):
        raise ValueError('Native Vercel lock must match all and only the API package versions')
    declarations = (ROOT / 'api/requirements.txt').read_text().replace('\\\n', ' ')
    hashes = {}
    for line in declarations.splitlines():
        match = re.match(r'([A-Za-z0-9_.-]+)==', line)
        if match:
            hashes[re.sub(r'[-_.]+', '-', match[1]).lower()] = set(re.findall(r'--hash=(sha256:[0-9a-f]{64})', line))
    for package in registry:
        if package['source']['registry'] != 'https://pypi.org/simple':
            raise ValueError('Vercel API package must come from the reviewed registry')
        artifacts = package.get('wheels', []) + ([package['sdist']] if 'sdist' in package else [])
        if not artifacts or any(a.get('hash') not in hashes[package['name']] for a in artifacts):
            raise ValueError(f"Vercel distribution hash differs: {package['name']}")
    builders = json.loads((ROOT / 'vercel.json').read_text())['builds']
    if next(b['use'] for b in builders if b['src'] == 'api/index.py') != '@vercel/python@25.1.3':
        raise ValueError('Review the Vercel Python builder before changing its pinned version')
    print(f'Hash-pinned locks verified: root={len(root)}, API={len(api)}, audit tools={len(security)}; shared versions match')


if __name__ == '__main__':
    verify()
