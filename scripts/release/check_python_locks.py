"""Reject unpinned/unhashed release dependencies and divergent shared API versions."""
from pathlib import Path
import re

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
    for name, version in api.items():
        if root.get(name) != version:
            raise ValueError(f'API dependency diverges from root lock: {name}')
    if (ROOT / '.python-version').read_text().strip() != '3.12':
        raise ValueError('Review runtime and lock targets together before changing Python')
    print(f'Hash-pinned locks verified: root={len(root)}, API={len(api)}, audit tools={len(security)}; shared versions match')


if __name__ == '__main__':
    verify()
