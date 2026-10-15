"""Local, on-demand GPT batch controls. No network, timer, trace order or outreach."""
import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
from datetime import date, timedelta


def claim(root, county, kind, day, legacy=None):
    """Commit before fetching. A crash/failure consumes this collection window."""
    if county not in ('Dallas', 'Collin') or kind not in ('tax', 'foreclosure'):
        raise ValueError('Unsupported source')
    current = date.fromisoformat(day)
    period = (current - timedelta(days=current.weekday()) if kind == 'tax' else current).isoformat()
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root / 'schedule.sqlite'
    with sqlite3.connect(path) as db:
        os.chmod(path, 0o600)
        db.execute('CREATE TABLE IF NOT EXISTS attempts (county TEXT, kind TEXT, period TEXT, day TEXT, PRIMARY KEY(county,kind,period))')
        # Carry forward prior worker attempts, including failed downloads.
        if kind == 'tax' and legacy:
            with sqlite3.connect(Path(legacy).resolve().as_uri() + '?mode=ro', uri=True) as old:
                prior = old.execute('SELECT 1 FROM jobs WHERE county=? AND day>=? AND day<=?', (county, period, day)).fetchone()
            if prior:
                db.execute('INSERT OR IGNORE INTO attempts VALUES(?,?,?,?)', (county, kind, period, day))
                return False
        result = db.execute('INSERT OR IGNORE INTO attempts VALUES(?,?,?,?)', (county, kind, period, day))
        return result.rowcount == 1


def safe(value):
    value = str(value or '')
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value


def write_csv(path, headers, rows):
    buffer = io.StringIO(newline='')
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows([[safe(value) for value in row] for row in rows])
    path.write_text(buffer.getvalue(), encoding='utf-8-sig')
    path.chmod(0o600)


def package_completed(source, root, day):
    """Archive completed reconciliation without creating re-order or campaign files."""
    date.fromisoformat(day)
    raw = Path(source).read_bytes()
    packet = json.loads(raw)
    if packet.get('processor') != 'bulk-reconcile/1.0' or not packet.get('provider_job_id'):
        raise ValueError('Expected a completed bulk reconciliation packet')
    items = packet.get('items')
    if not isinstance(items, list) or not items or len(items) > 500:
        raise ValueError('Expected 1–500 completed properties')
    if len({r['parcel_id'] for r in items}) != len(items):
        raise ValueError('Duplicate property identity')
    properties, held, excluded = [], [], []
    for row in items:
        if row.get('trace_again') is not False or row.get('outreach_authorized') is not False:
            raise ValueError('Reconciliation must prohibit reorders and outreach')
        identity = row['identity']
        properties.append([row['parcel_id'], identity['property_address'], identity['city'],
                           identity['zip'], row['owner_name'], 'Complete — do not reorder',
                           row['current_listing']['stage'], '; '.join(row['exceptions'])])
        seen = set()
        for contact in row['contacts']:
            phone = contact.get('phone', '')
            if not phone or phone in seen:
                continue
            seen.add(phone)
            dnc = contact.get('dnc_status', 'unknown')
            if dnc != 'clear':
                excluded.append([row['parcel_id'], phone[-4:], dnc,
                                 'DNC listed' if dnc == 'listed' else 'DNC clearance missing'])
            else:
                held.append([row['parcel_id'], contact.get('name', ''), phone.removeprefix('+'),
                             'Channel clearance, current suppression and provider warnings require review'])
    digest = hashlib.sha256(raw).hexdigest()
    folder = Path(root) / day / ('completed-' + digest[:16])
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    headers = ['Parcel ID', 'Property address', 'City', 'ZIP', 'Owner', 'Skip trace', 'Listing evidence', 'Remaining checks']
    summary = [['Batch date', day], ['Evidence date', packet['day']], ['Provider job', packet['provider_job_id']],
               ['Completed properties', len(items)], ['New trace orders', 0], ['Outreach-ready contacts', 0],
               ['Excluded phone records', len(excluded)], ['DNC-clear contacts on other holds', len(held)],
               ['Scope', 'Saved evidence only; not a fresh county collection'],
               ['Budget', '$50 cumulative cap; verify current balance and reservations before any new order']]
    workbook = {'title': 'WholesaleOS batch ' + day, 'source_sha256': digest, 'sheets': [
        {'name': 'Batch status', 'headers': ['Item', 'Value'], 'rows': summary},
        {'name': 'Completed properties', 'headers': headers, 'rows': properties},
        {'name': 'Excluded phones', 'headers': ['Parcel ID', 'Last four', 'DNC status', 'Reason'], 'rows': excluded},
    ]}
    (folder / 'workbook-input.json').write_text(json.dumps(workbook, indent=2), encoding='utf-8')
    (folder / 'workbook-input.json').chmod(0o600)
    write_csv(folder / 'contacts-on-hold.csv', ['ParcelID', 'Name', 'Phone', 'HoldReason'], held)
    # Deliberately header-only until authoritative per-channel clearance is wired in.
    write_csv(folder / 'dialer-ready.csv', ['LeadID', 'Name', 'Phone', 'CallReady'], [])
    write_csv(folder / 'sms-ready.csv', ['LeadID', 'Name', 'Phone', 'SMSReady'], [])
    receipt = {'source_sha256': digest, 'day': day, 'source_day': packet['day'],
               'properties': len(items), 'excluded_phones': len(excluded), 'held_contacts': len(held),
               'new_trace_orders': 0, 'outreach_ready': 0, 'fresh_collection': False,
               'crm_delivery_performed': False, 'provider_upload_performed': False}
    (folder / 'receipt.json').write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    (folder / 'receipt.json').chmod(0o600)
    return folder, receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    fetch = commands.add_parser('claim')
    fetch.add_argument('--root', required=True)
    fetch.add_argument('--county', required=True, choices=['Dallas', 'Collin'])
    fetch.add_argument('--kind', required=True, choices=['tax', 'foreclosure'])
    fetch.add_argument('--day', required=True)
    fetch.add_argument('--legacy')
    pack = commands.add_parser('package-completed')
    pack.add_argument('--source', required=True)
    pack.add_argument('--root', required=True)
    pack.add_argument('--day', required=True)
    args = vars(parser.parse_args())
    action = args.pop('action')
    if action == 'claim':
        print(json.dumps({'collection_allowed': claim(**args)}))
    else:
        folder, receipt = package_completed(**args)
        print(json.dumps({'folder': str(folder), **receipt}))
