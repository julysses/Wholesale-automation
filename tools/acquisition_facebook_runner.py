"""Disabled-by-default supervised Facebook intake runner; never installs a schedule.

Run with ``python -m tools.acquisition_facebook_runner`` only in an explicitly
approved environment. Each cycle calls the existing one-inquiry leased worker.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
import signal
import uuid

from tools.acquisition_facebook_worker import WorkerUnavailable, process_facebook_inquiry

CYCLE_TIMEOUT_SECONDS = 60
CLASSIFICATIONS = {'qualified', 'incomplete', 'duplicate', 'unqualified', 'requires_human_review'}
RETRY_REASONS = {'PROVIDER_RATE_LIMIT', 'PROVIDER_UNAVAILABLE', 'PROVIDER_TIMEOUT', 'PERSISTENCE_UNAVAILABLE'}
REVIEW_REASONS = {'CREDENTIALS_INVALID', 'PERMISSION_DENIED', 'INVALID_PROVIDER_DATA',
                  'IDENTITY_CONFLICT', 'UNSUPPORTED_EVENT', 'RETRY_EXHAUSTED', 'PAYLOAD_EXPIRED'}


def safe_result(raw):
    """Only allowlisted aggregate fields reach supervisor logs, never raw errors."""
    if not isinstance(raw, dict):
        raise ValueError('Unexpected result')
    status = raw.get('status')
    if status == 'idle' and set(raw) == {'status'}:
        return raw
    if (status == 'completed' and set(raw) == {'status', 'classification', 'duplicate'}
            and raw.get('classification') in CLASSIFICATIONS and type(raw.get('duplicate')) is bool):
        return raw
    if (status in ('retry', 'review') and set(raw) == {'status', 'reason_code'}
            and raw.get('reason_code') in (RETRY_REASONS if status == 'retry' else REVIEW_REASONS)):
        return raw
    raise ValueError('Unexpected result')


def emit(record):
    print(json.dumps(record, sort_keys=True), flush=True)


async def run(*, max_cycles=1, interval_seconds=30, stop=None, report=emit):
    if type(max_cycles) is not int or not 1 <= max_cycles <= 10000:
        raise ValueError('Cycles must be between 1 and 10000')
    if type(interval_seconds) is not int or not 30 <= interval_seconds <= 3600:
        raise ValueError('Interval must be between 30 and 3600 seconds')
    stop = stop or asyncio.Event()
    run_id = str(uuid.uuid4())

    def status(event, cycle, **fields):
        report({'component': 'acquisition_facebook_runner', 'run_id': run_id,
                'at': datetime.now(timezone.utc).isoformat(), 'event': event, 'cycle': cycle, **fields})

    for cycle in range(1, max_cycles + 1):
        if stop.is_set():
            status('stopped', cycle, outcome='stop_requested')
            return 0
        if os.getenv('ACQUISITION_FACEBOOK_RUNNER_ENABLED', '').lower() != 'true':
            status('stopped', cycle, outcome='runner_disabled')
            return 78
        status('cycle_started', cycle)
        try:
            # The worker rechecks its own activation/configuration every cycle.
            # Cancellation/unknown completion must leave the original SQL lease
            # alone; no new request, forced reset, deferral or rapid retry here.
            raw = await asyncio.wait_for(process_facebook_inquiry(), timeout=CYCLE_TIMEOUT_SECONDS)
            result = safe_result(raw)
        except (WorkerUnavailable, TimeoutError, ValueError, TypeError):
            status('stopped', cycle, outcome='operation_unconfirmed')
            return 1
        except Exception:
            status('stopped', cycle, outcome='operation_unconfirmed')
            return 1
        status('cycle_finished', cycle, **result)
        if result['status'] == 'review':
            status('stopped', cycle, outcome='review_required')
            return 2
        if stop.is_set() or cycle == max_cycles:
            status('stopped', cycle, outcome='stop_requested' if stop.is_set() else 'cycle_limit')
            return 0
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
    return 0


async def supervised(args):
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    installed = []
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(signum, stop.set)
            installed.append(signum)
        return await run(max_cycles=args.max_cycles, interval_seconds=args.interval_seconds, stop=stop)
    finally:
        for signum in installed:
            loop.remove_signal_handler(signum)


def bounded_integer(low, high):
    def parse(value):
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError('Expected an integer') from None
        if not low <= number <= high:
            raise argparse.ArgumentTypeError(f'Expected {low} through {high}')
        return number
    return parse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--max-cycles', type=bounded_integer(1, 10000), default=1)
    parser.add_argument('--interval-seconds', type=bounded_integer(30, 3600), default=30)
    args = parser.parse_args()
    return asyncio.run(supervised(args))


if __name__ == '__main__':
    raise SystemExit(main())
