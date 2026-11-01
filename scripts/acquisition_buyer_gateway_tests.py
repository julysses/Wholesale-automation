"""Focused real gateway recheck on a disposable complete candidate catalog.

This uses the inventory runner's migration owner, not the production-role upgrade
rehearsal. It supplements, and never replaces, that populated acceptance run.
"""
import json
import sys
from pathlib import Path
from acquisition_buyer_catalog_inventory import main
from rehearse_acquisition_baseline import PG
from rehearse_acquisition_upgrade import seed
from acquisition_postgrest import run_postgrest


def probe(db):
    seed(db)
    result = run_postgrest(db, sys.argv[1], PG)
    result['scope'] = 'Focused actual gateway recheck on disposable full candidate catalog; not migration-role or populated-upgrade acceptance'
    result['production_changed'] = False
    Path('docs/acquisition-automation/evidence/2026-11-01-buyer-gateway-focused-result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({'real_postgrest':result['real_postgrest'],'checks':len(result['checks']),'scope':result['scope']}))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Supply the absolute path to reviewed PostgREST 16.5')
    main(probe)
