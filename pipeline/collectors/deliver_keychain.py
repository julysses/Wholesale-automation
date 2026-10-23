"""Deliver saved manifests to the rehearsal project using source-scoped macOS Keychain credentials.
Never provisions credentials, changes sources, spends tracing credit or sends outreach.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess

REHEARSAL_PROJECT = 'tbhwxgfzbiaqjurghntj'
SOURCES = {f'tx-{county}-{kind}' for county in ('dallas', 'collin') for kind in ('pre_foreclosure', 'tax_delinquent')}

def deliver(directory, coverage=None):
    directory = Path(directory).resolve(strict=True)
    files = sorted(directory.glob('batch-[0-9][0-9][0-9][0-9].json'))
    if not files:
        raise ValueError('No saved manifest batches')
    keys = set()
    for file in files:
        if file.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('Manifest exceeds ingestion limit')
        keys.add(json.loads(file.read_text())['source_key'])
    if len(keys) != 1 or not keys.issubset(SOURCES):
        raise ValueError('One accepted county source required')
    key = next(iter(keys))
    secret = subprocess.run(['/usr/bin/security', 'find-generic-password', '-a', key,
        '-s', 'wholesaleos.rehearsal.collector.' + key, '-w'], capture_output=True, text=True, timeout=20)
    if secret.returncode or not secret.stdout.strip():
        raise RuntimeError('Scoped rehearsal credential unavailable; do not replace it with an admin key')
    environment = {**os.environ, 'INGEST_KEY_ID': key, 'INGEST_TOKEN': secret.stdout.strip()}
    client = Path(__file__).with_name('deliver.mjs')
    extra = []
    if coverage is not None:
        coverage = Path(coverage).resolve(strict=True)
        if coverage.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('Coverage ledger exceeds limit')
        extra = [str(coverage)]
    # The shared client checks every batch before network access, saves the retry
    # journal, and requires exact durable acknowledgements. It does not print secrets.
    return subprocess.run(['node', str(client), str(directory), REHEARSAL_PROJECT, *extra], env=environment).returncode

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest_directory')
    parser.add_argument('--coverage', help='Reviewed complete-coverage ledger, when applicable')
    args = parser.parse_args()
    try:
        raise SystemExit(deliver(args.manifest_directory, args.coverage))
    except Exception as exc:
        # Provider/keychain output and data contents must not become error logs.
        raise SystemExit('Rehearsal delivery not confirmed (' + type(exc).__name__ + '). Preserve saved manifests and receipts.')
