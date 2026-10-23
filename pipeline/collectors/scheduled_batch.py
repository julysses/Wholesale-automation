"""Local, on-demand GPT batch controls. No network, timer, trace order or outreach."""
import argparse
import csv
import hashlib
import io
import json
import os
import re
from pathlib import Path
import sqlite3
from datetime import date, timedelta

# PropStream's accepted contact-import mapping, then Retell's documented CSV
# contract. Keep owner_name/property_address aligned with our Retell agent API.
PROPSTREAM_HEADERS = ['First Name', 'Last Name', 'Email', 'Phone', 'Mobile Phone', 'Landline',
                     'Street Address', 'City', 'State', 'Zip', 'Mail Street Address',
                     'Mail City', 'Mail State', 'Mail Zip', 'Mail Address Same', 'Type', 'Status']
RETELL_HEADERS = ['phone number', 'owner_name', 'contact_name', 'property_address',
                  'property_city', 'property_state', 'property_zip', 'county',
                  'lead_id', 'parcel_id', 'trace_request_id', 'follow_up_task_id',
                  'agent_name', 'agency_name', 'metadata']


def validate_upload(path, provider):
    """Validate transport format only. Never grants tracing/channel authorization."""
    expected = {'propstream': PROPSTREAM_HEADERS, 'retell': RETELL_HEADERS}[provider]
    errors, seen, count = [], set(), 0
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != expected:
            return {'format_valid': False, 'rows': 0, 'errors': ['header_contract_mismatch'],
                    'dispatch_authorized': False}
        for line, row in enumerate(reader, 2):
            count += 1
            reasons = []
            if None in row or any(value is None for value in row.values()):
                errors.append({'line': line, 'reasons': ['column_count_mismatch']})
                continue
            if provider == 'propstream':
                if not (row['First Name'].strip() or row['Last Name'].strip()):
                    reasons.append('seller_name_missing')
                if any(not row[k].strip() for k in ('Street Address', 'City', 'State', 'Zip')):
                    reasons.append('property_address_incomplete')
                if row['State'] != 'TX' or not re.fullmatch(r'\d{5}(?:-\d{4})?', row['Zip']):
                    reasons.append('invalid_state_or_zip')
                key = tuple(row[k].strip().casefold() for k in ('Street Address', 'City', 'State', 'Zip'))
            else:
                if not re.fullmatch(r'\+1[2-9]\d{2}[2-9]\d{6}', row['phone number']):
                    reasons.append('invalid_us_e164_phone')
                required = [k for k in RETELL_HEADERS if k != 'metadata']
                if any(not row[k].strip() for k in required):
                    reasons.append('required_context_missing')
                if row['property_state'] != 'TX' or not re.fullmatch(r'\d{5}(?:-\d{4})?', row['property_zip']):
                    reasons.append('invalid_state_or_zip')
                if row['county'] not in ('Dallas', 'Collin'):
                    reasons.append('unsupported_county')
                try:
                    metadata = json.loads(row['metadata'])
                    ids = ('lead_id', 'parcel_id', 'trace_request_id', 'follow_up_task_id')
                    if not isinstance(metadata, dict) or any(not row[k] or metadata.get(k) != row[k] for k in ids):
                        reasons.append('crm_metadata_mismatch')
                except (ValueError, TypeError):
                    reasons.append('invalid_metadata_json')
                key = row['phone number']
            if key in seen:
                reasons.append('duplicate_property' if provider == 'propstream' else 'duplicate_recipient')
            seen.add(key)
            if reasons:
                errors.append({'line': line, 'reasons': reasons})
    return {'format_valid': not errors, 'rows': count, 'errors': errors,
            'empty_template': count == 0, 'dispatch_authorized': False,
            'remaining_gate': 'Fresh CRM eligibility, suppression, history and provider acceptance required'}


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
        {'name': 'PropStream upload', 'headers': PROPSTREAM_HEADERS, 'rows': []},
        {'name': 'Retell call upload', 'headers': RETELL_HEADERS, 'rows': []},
    ]}
    (folder / 'workbook-input.json').write_text(json.dumps(workbook, indent=2), encoding='utf-8')
    (folder / 'workbook-input.json').chmod(0o600)
    write_csv(folder / 'contacts-on-hold.csv', ['ParcelID', 'Name', 'Phone', 'HoldReason'], held)
    # Deliberately header-only until authoritative per-channel clearance is wired in.
    write_csv(folder / 'dialer-ready.csv', ['LeadID', 'Name', 'Phone', 'CallReady'], [])
    write_csv(folder / 'sms-ready.csv', ['LeadID', 'Name', 'Phone', 'SMSReady'], [])
    write_csv(folder / 'propstream-upload.csv', PROPSTREAM_HEADERS, [])
    write_csv(folder / 'retell-call-upload.csv', RETELL_HEADERS, [])
    (folder / 'UPLOAD-README.txt').write_text(
        'STAGE 1: propstream-upload.csv contains only newly eligible, never-traced properties.\n'
        'This completed batch has zero such rows. Do not re-upload the completed-property sheet.\n'
        'STAGE 2: retell-call-upload.csv contains only cleared call recipients after tracing.\n'
        'This batch has zero cleared recipients. DNC listed and unknown numbers are excluded.\n'
        'Retell CSV requires the exact phone number header and E.164 values such as +12145551234.\n'
        'Do not add an apostrophe to E.164 phone values in the machine upload CSV.\n'
        'Other columns are agent variables. owner_name and property_address match WholesaleOS.\n'
        'metadata must be JSON carrying lead, parcel, trace and follow-up IDs for CRM reconciliation.\n'
        'Before populated export, verify current suppression, identity, consent/channel receipts and expiry.\n'
        'Retell agent, outbound number, calling windows and draft import must still be verified in account.\n'
        'SMS needs separate eligibility and platform setup; this is a call CSV, not an SMS campaign.\n'
        'Official format: https://docs.retellai.com/deploy/make-batch-call\n', encoding='utf-8')
    (folder / 'UPLOAD-README.txt').chmod(0o600)
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
    validate = commands.add_parser('validate-upload')
    validate.add_argument('--path', required=True)
    validate.add_argument('--provider', required=True, choices=['propstream', 'retell'])
    args = vars(parser.parse_args())
    action = args.pop('action')
    if action == 'claim':
        print(json.dumps({'collection_allowed': claim(**args)}))
    elif action == 'validate-upload':
        result = validate_upload(**args)
        print(json.dumps(result))
        raise SystemExit(0 if result['format_valid'] else 2)
    else:
        folder, receipt = package_completed(**args)
        print(json.dumps({'folder': str(folder), **receipt}))
