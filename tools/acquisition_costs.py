"""Deterministic campaign cost projection over scoped, persisted daily evidence.

This module does not authenticate evidence, fetch provider data, convert currency,
write records, or grant authority. The repository adapter must enforce those
boundaries before calling it. A partial/withdrawn latest revision never falls
back to a superseded complete revision.
"""
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re

VERSION = 'acquisition-cost-coverage-v1'
MAX_RECORDS = 10000
MAX_DAYS = 366
MAX_MINOR = 100_000_000_000_000


def _uuid(value):
    if not isinstance(value, str):
        raise ValueError('Invalid evidence identity')
    try:
        if str(UUID(value)) != value:
            raise ValueError('Noncanonical identity')
    except (ValueError, AttributeError):
        raise ValueError('Invalid evidence identity') from None
    return value


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('Invalid reporting date')
    return date.fromisoformat(value)


def _stamp(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError('Invalid observation time')
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('Timezone required')
        return stamp.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError('Invalid observation time') from None


def campaign_cost_coverage(*, workspace_id, campaign_id, start_date, end_date,
                           reporting_timezone, currency, as_of, records):
    """Inclusive daily window, USD cents only; missing coverage yields null total.

    Each revision must supply id, workspace_id, campaign_id, date, revision,
    reporting_timezone, currency, amount_minor, coverage, observed_at,
    evidence_ref and evidence_hash. Revision ordering is ledger sequence, never
    caller list order or observation time. Exact repeated rows are deduplicated;
    conflicting UUIDs or day/revision identities reject the entire projection.
    """
    _uuid(workspace_id); _uuid(campaign_id)
    cutoff = _stamp(as_of)
    start, end = _day(start_date), _day(end_date)
    if end < start or (end-start).days >= MAX_DAYS:
        raise ValueError('Reporting window must contain 1–366 days')
    if currency != 'USD':
        raise ValueError('Unsupported reporting currency')
    try:
        zone = ZoneInfo(reporting_timezone)
    except (ZoneInfoNotFoundError, TypeError, ValueError):
        raise ValueError('Invalid reporting timezone') from None
    if not isinstance(records, list) or len(records) > MAX_RECORDS:
        raise ValueError('Evidence batch unavailable or too large')
    latest, identities, revisions = {}, {}, {}
    for record in records:
        if not isinstance(record, dict):
            raise ValueError('Invalid cost evidence')
        identity = _uuid(record.get('id'))
        if record.get('workspace_id') != workspace_id or record.get('campaign_id') != campaign_id:
            raise ValueError('Cost evidence scope mismatch')
        if record.get('currency') != currency or record.get('reporting_timezone') != reporting_timezone:
            raise ValueError('Cost evidence unit mismatch')
        day = _day(record.get('date'))
        if not start <= day <= end:
            raise ValueError('Cost evidence outside reporting window')
        revision, amount, coverage = record.get('revision'), record.get('amount_minor'), record.get('coverage')
        if type(revision) is not int or not 1 <= revision <= 2147483647:
            raise ValueError('Invalid cost revision')
        if coverage not in ('complete', 'partial', 'withdrawn'):
            raise ValueError('Invalid cost coverage')
        if coverage == 'withdrawn':
            if amount is not None:
                raise ValueError('Withdrawn cost must be unavailable')
        elif type(amount) is not int or not 0 <= amount <= MAX_MINOR:
            raise ValueError('Invalid amount in minor units')
        observed = _stamp(record.get('observed_at'))
        if observed > cutoff:
            raise ValueError('Cost evidence observed after reporting cutoff')
        if coverage == 'complete' and observed.astimezone(zone).date() <= day:
            raise ValueError('Complete daily cost requires an observation after that local day')
        if not isinstance(record.get('evidence_ref'), str) or not 1 <= len(record['evidence_ref']) <= 1000 or not record['evidence_ref'].strip():
            raise ValueError('Cost evidence reference required')
        if not isinstance(record.get('evidence_hash'), str) or not re.fullmatch('[a-f0-9]{64}', record['evidence_hash']):
            raise ValueError('Cost evidence fingerprint required')
        if identity in identities and identities[identity] != record:
            raise ValueError('Conflicting cost evidence identity')
        key = (day, revision)
        if key in revisions and revisions[key] != identity:
            raise ValueError('Conflicting daily revision')
        identities[identity] = record
        revisions[key] = identity
        if day not in latest or latest[day]['revision'] < revision:
            latest[day] = record
    days, observed_total, reasons = [], 0, set()
    for offset in range((end-start).days+1):
        day = start+timedelta(days=offset)
        row = latest.get(day)
        coverage = row['coverage'] if row else 'missing'
        amount = row['amount_minor'] if row else None
        if amount is not None:
            observed_total += amount
        if coverage != 'complete':
            reasons.add('COST_'+coverage.upper())
        days.append({'date': day.isoformat(), 'coverage': coverage, 'amount_minor': str(amount) if amount is not None else None,
                     'revision_id': row['id'] if row else None, 'revision': row['revision'] if row else None,
                     'evidence_hash': row['evidence_hash'] if row else None,
                     'observed_at': _stamp(row['observed_at']).isoformat() if row else None})
    complete = not reasons
    return {'projection_version': VERSION, 'workspace_id': workspace_id, 'campaign_id': campaign_id,
            'start_date': start_date, 'end_date': end_date, 'reporting_timezone': reporting_timezone,
            'currency': currency, 'as_of': cutoff.isoformat(), 'minor_unit_exponent': 2, 'status': 'complete' if complete else 'incomplete',
            'reason_codes': sorted(reasons), 'total_cost_minor': str(observed_total) if complete else None,
            'observed_cost_minor': str(observed_total) if any(d['amount_minor'] is not None for d in days) else None,
            'complete_days': sum(d['coverage'] == 'complete' for d in days), 'requested_days': len(days),
            'days': days, 'cost_per_lead_minor': None, 'qualified_cost_per_lead_minor': None,
            'denominator_status': 'NOT_RECONCILED', 'execution_authorized': False}
