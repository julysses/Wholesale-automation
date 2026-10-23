from pathlib import Path
import shutil

import pytest

from scripts.release import check_python_locks as locks


@pytest.fixture
def release_inputs(tmp_path, monkeypatch):
    for name in ('requirements.txt', 'api/requirements.txt', 'requirements-security.txt',
                 'requirements-vercel-build.txt', '.python-version', 'api/.python-version',
                 'api/pyproject.toml', 'api/uv.lock', 'vercel.json'):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(locks.ROOT / name, target)
    monkeypatch.setattr(locks, 'ROOT', tmp_path)
    return tmp_path


def test_native_vercel_and_pip_locks_agree(release_inputs):
    locks.verify()


@pytest.mark.parametrize('name,old,new', [
    ('api/.python-version', '3.12', '3.13'),
    ('api/pyproject.toml', 'twilio==9.11.2', 'twilio==9.11.3'),
    ('api/uv.lock', 'version = "9.11.2"', 'version = "9.11.3"'),
    ('api/uv.lock', 'sha256:', 'sha256:invalid'),
    ('api/uv.lock', 'https://pypi.org/simple', 'https://unreviewed.invalid/simple'),
    ('requirements-vercel-build.txt', 'uv==0.13.5', 'uv==0.10.11'),
    ('vercel.json', '@vercel/python@25.1.3', '@vercel/python'),
])
def test_release_gate_rejects_target_version_hash_or_registry_drift(release_inputs, name, old, new):
    path = release_inputs / name
    content = path.read_text()
    assert old in content
    path.write_text(content.replace(old, new, 1))
    with pytest.raises(ValueError):
        locks.verify()
