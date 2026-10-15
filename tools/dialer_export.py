"""Bulk local preparation only. Never dispatches or infers channel clearance."""
import csv
import io
import zipfile
from datetime import datetime, timezone
from tools.facebook_consent import normalize_us_phone
from tools.retell_sms import INITIAL_MESSAGE, SMS_REVIEW_HEADERS, sms_review_row


def csv_bytes(headers, rows):
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(headers)
    for row in rows:
        # Provider/source text must not become a spreadsheet formula.
        writer.writerow(["'" + str(v) if str(v).lstrip().startswith(('=', '+', '-', '@')) else str(v) for v in row])
    return out.getvalue().encode('utf-8-sig')


def prepare_export(items, now=None):
    now = now or datetime.now(timezone.utc)
    review, excluded, seen = [], [], set()
    for lead in items:
        lead_id = lead['lead_id']
        request = lead.get('request') or {}
        contacts = lead.get('contacts') or []
        common = [lead_id, lead.get('address_std', ''), lead.get('county', '')]
        if request.get('state') != 'completed':
            excluded.append(common + ['', 'Skip trace has no completed receipt'])
            continue
        if lead.get('dnc') is not False or lead.get('status') in ('dnc', 'dead', 'sold', 'under_contract'):
            excluded.append(common + ['', 'Lead suppressed or suppression status unavailable'])
            continue
        if not contacts:
            excluded.append(common + ['', 'Completed trace returned no contacts; do not reorder'])
        for contact in contacts:
            reason = None
            try:
                phone = normalize_us_phone(contact.get('phone'))
                expires = datetime.fromisoformat(contact['expires_at'].replace('Z', '+00:00'))
                if expires.tzinfo is None or expires <= now:
                    reason = 'Contact evidence expired'
            except (ValueError, KeyError, TypeError):
                reason = 'Missing valid phone or expiry evidence'
            if contact.get('dnc_status') not in ('clear', 'unknown'):
                reason = 'DNC listed or unrecognized status'
            if reason:
                excluded.append(common + [contact.get('id', ''), reason])
                continue
            key = (lead_id, phone)
            if key in seen:
                continue
            seen.add(key)
            review.append([lead_id, contact.get('name', ''), phone.removeprefix('+'),
                           lead.get('address_std', ''), lead.get('city', ''), 'TX', lead.get('zip', ''),
                           lead.get('county', ''), request.get('id', ''),
                           (lead.get('handoff') or {}).get('follow_up_task_id', ''),
                           contact.get('dnc_status', 'unknown'), 'false', 'false', 'Channel clearance and provider warnings require review'])
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('contacts-for-review.csv', csv_bytes(
            ['LeadID','ContactName','Phone','PropertyAddress','City','State','Zip','County',
             'TraceRequestID','FollowUpTaskID','ProviderDNCStatus','CallReady','SMSReady','HoldReason'], review))
        archive.writestr('retell-sms-review.csv', csv_bytes(SMS_REVIEW_HEADERS, [sms_review_row(row) for row in review]))
        archive.writestr('sms-message-template.txt', INITIAL_MESSAGE + '\n')
        archive.writestr('excluded.csv', csv_bytes(['LeadID','PropertyAddress','County','ContactID','Reason'], excluded))
        archive.writestr('README.txt',
            'WholesaleOS bulk dialer preparation\n'
            f'Created: {now.isoformat()}\nReview contacts: {len(review)}\nExclusions: {len(excluded)}\n'
            'retell-sms-review.csv contains held message drafts, NOT a Retell upload file.\n'
            'Unresolved first_name/sender_name tokens must not be sent; traced contact names are not confirmed sellers.\n'
            'This is a review package, not an approved campaign import. No calls or SMS are authorized.\n'
            'CallReady and SMSReady remain false: the current county workflow has no durable per-channel clearance receipt.\n'
            'Review provider warnings, ownership/current-sale evidence and channel eligibility before campaign use.\n'
            'DNC-listed, expired, suppressed and incomplete results are excluded from the contact file.\n'
            'Unknown DNC status remains a review hold, never permission to call.\n'
            'Keep this private. Re-export before use; suppression and evidence can change. No provider was contacted or charged.\n')
    return output.getvalue()
