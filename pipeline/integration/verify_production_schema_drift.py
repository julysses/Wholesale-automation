"""Compare fresh read-only production shapes with the locally restored release."""
import json
import re
from pathlib import Path

from production_schema import ROOT
from tests.local_journey_db import Database


def normalized_acl(value, local=False):
    if value is None:
        return None
    grants = {}
    for entry in value.strip('{}').split(','):
        role, privileges = entry.split('=', 1)
        role = role.strip('"')
        if local and role in {'test_admin', 'pg_database_owner'}:
            role = 'postgres'
        rights = privileges.split('/')[0]
        grants.setdefault(role, set()).update(re.findall(r'.\*?', rights))
    return {role: sorted(rights) for role, rights in sorted(grants.items())}


def canonical(value, local=False):
    if isinstance(value, dict):
        return {key: normalized_acl(item, local) if key == 'acl' else canonical(item, local)
                for key, item in value.items()}
    if isinstance(value, list):
        return [canonical(row, local) for row in value]
    return value


def verify(db):
    sql = (ROOT/'scripts/release/production_schema_shapes.sql').read_text()
    sql = sql.replace('BEGIN READ ONLY;', '').replace('COMMIT;', '')
    sql = re.sub(r'SET LOCAL search_path=[^;]+;', '', sql)
    db.query('SET search_path=public,extensions')
    expected = db.query(sql)[0]['evidence']
    observed = json.loads((ROOT/'docs/integration/production-schema-shapes-2026-10-22.json').read_text())
    categories = ['tables','constraints','indexes','triggers','policies','views','schema_acls','default_acls','view_security']
    results = {}
    for category in categories:
        left, right = canonical(expected[category], local=True), canonical(observed[category])
        if isinstance(left, list):
            left = sorted(left, key=lambda row: json.dumps(row, sort_keys=True))
        if isinstance(right, list):
            right = sorted(right, key=lambda row: json.dumps(row, sort_keys=True))
        if left != right:
            left_rows = {json.dumps(row, sort_keys=True) for row in left or []}
            right_rows = {json.dumps(row, sort_keys=True) for row in right or []}
            raise AssertionError(json.dumps({'category':category,'local_only':sorted(left_rows-right_rows),'production_only':sorted(right_rows-left_rows)}, indent=2))
        results[category] = len(observed[category] or [])
    print(json.dumps({'production_schema_drift':'passed','captured_at':observed['captured_at'],
        'comparison':'fresh production versus saved catalog restored with released Facebook migration',
        'matched_categories':results,'owner_normalization':'expected local test_admin and pg_database_owner privileges merged into postgres; observed role names unchanged; grantor names ignored; privilege and grant-option rights retained',
        'excluded':['functions compared in separate production fingerprint evidence','sequences and enums not queried here'],
        'production_rows_copied':0}), flush=True)


if __name__ == '__main__':
    db = Database()
    try:
        verify(db)
    finally:
        db.connection.close()
