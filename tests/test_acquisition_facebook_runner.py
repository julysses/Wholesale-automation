import asyncio
import json
import os
import subprocess
import sys

import pytest

from tools import acquisition_facebook_runner as runner
from tools.acquisition_facebook_worker import WorkerUnavailable


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setenv('ACQUISITION_FACEBOOK_RUNNER_ENABLED', 'true')
    state = {'calls': 0, 'rows': [], 'result': {'status': 'idle'}}
    async def process():
        state['calls'] += 1
        if 'error' in state:
            raise state['error']
        if 'stop' in state:
            state['stop'].set()
        return state['result']
    monkeypatch.setattr(runner, 'process_facebook_inquiry', process)
    return state


def execute(harness, **kwargs):
    return asyncio.run(runner.run(report=harness['rows'].append, **kwargs))


def test_disabled_runner_never_calls_worker(harness, monkeypatch):
    monkeypatch.delenv('ACQUISITION_FACEBOOK_RUNNER_ENABLED')
    assert execute(harness) == 78
    assert harness['calls'] == 0
    assert harness['rows'][-1]['outcome'] == 'runner_disabled'


@pytest.mark.parametrize('result', [
    {'status': 'idle'}, {'status': 'completed', 'classification': 'incomplete', 'duplicate': False},
    {'status': 'retry', 'reason_code': 'PROVIDER_RATE_LIMIT'},
])
def test_single_cycle_logs_only_confirmed_result(harness, result):
    harness['result'] = result
    assert execute(harness) == 0
    assert harness['calls'] == 1
    assert [r['event'] for r in harness['rows']] == ['cycle_started', 'cycle_finished', 'stopped']
    assert harness['rows'][1]['status'] == result['status']
    assert len({r['run_id'] for r in harness['rows']}) == 1


@pytest.mark.parametrize('error', [WorkerUnavailable('private token'), RuntimeError('seller address'), TimeoutError('secret')])
def test_uncertain_outcome_stops_without_reprocessing_or_error_disclosure(harness, error):
    harness['error'] = error
    assert execute(harness, max_cycles=3) == 1
    assert harness['calls'] == 1
    logs = json.dumps(harness['rows'])
    assert str(error) not in logs
    assert harness['rows'][-1]['outcome'] == 'operation_unconfirmed'


def test_review_stops_and_alerts_supervisor(harness):
    harness['result'] = {'status': 'review', 'reason_code': 'CREDENTIALS_INVALID'}
    assert execute(harness, max_cycles=3) == 2
    assert harness['calls'] == 1
    assert harness['rows'][-1]['outcome'] == 'review_required'


@pytest.mark.parametrize('result', [
    {'status': 'completed', 'classification': 'incomplete', 'duplicate': 1},
    {'status': 'idle', 'token': 'private'}, {'status': 'review', 'reason_code': 'private'},
    {'status': 'retry', 'reason_code': 'CREDENTIALS_INVALID'}, [], None,
])
def test_untrusted_result_does_not_enter_logs_or_continue(harness, result):
    harness['result'] = result
    assert execute(harness, max_cycles=3) == 1
    assert 'private' not in json.dumps(harness['rows'])
    assert harness['calls'] == 1


def test_stop_during_work_finishes_exact_cycle_and_does_not_claim_again(harness):
    async def scenario():
        stop = asyncio.Event()
        harness['stop'] = stop
        return await runner.run(max_cycles=3, stop=stop, report=harness['rows'].append)
    assert asyncio.run(scenario()) == 0
    assert harness['calls'] == 1
    assert harness['rows'][-1]['outcome'] == 'stop_requested'


def test_preexisting_stop_prevents_claim(harness):
    async def scenario():
        stop = asyncio.Event(); stop.set()
        return await runner.run(stop=stop, report=harness['rows'].append)
    assert asyncio.run(scenario()) == 0
    assert harness['calls'] == 0


def test_total_cycle_timeout_stops_without_claim_retry(harness, monkeypatch):
    monkeypatch.setattr(runner, 'CYCLE_TIMEOUT_SECONDS', .01)
    async def slow():
        harness['calls'] += 1
        await asyncio.Event().wait()
    monkeypatch.setattr(runner, 'process_facebook_inquiry', slow)
    assert execute(harness, max_cycles=3) == 1
    assert harness['calls'] == 1


@pytest.mark.parametrize('kwargs', [{'max_cycles': 0}, {'max_cycles': True}, {'max_cycles': 10001},
                                    {'interval_seconds': 0}, {'interval_seconds': 3601}])
def test_invalid_runtime_bounds_never_claim(harness, kwargs):
    with pytest.raises(ValueError): execute(harness, **kwargs)
    assert harness['calls'] == 0


def test_real_cli_defaults_to_disabled_without_secrets():
    env = {k: v for k, v in os.environ.items() if not k.startswith(('ACQUISITION_', 'SUPABASE_', 'FACEBOOK_'))}
    result = subprocess.run([sys.executable, '-m', 'tools.acquisition_facebook_runner'], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 78
    assert json.loads(result.stdout)['outcome'] == 'runner_disabled'
    assert result.stderr == ''


def test_disable_between_cycles_prevents_another_claim(harness, monkeypatch):
    class Pause:
        def is_set(self): return False
        async def wait(self):
            monkeypatch.setenv('ACQUISITION_FACEBOOK_RUNNER_ENABLED', 'false')
    assert execute(harness, max_cycles=3, stop=Pause()) == 78
    assert harness['calls'] == 1
    assert harness['rows'][-1]['outcome'] == 'runner_disabled'


def test_stop_while_waiting_does_not_start_another_cycle(harness):
    async def scenario():
        stop = asyncio.Event()
        def report(row):
            harness['rows'].append(row)
            if row['event'] == 'cycle_finished':
                asyncio.get_running_loop().call_soon(stop.set)
        return await runner.run(max_cycles=3, stop=stop, report=report)
    assert asyncio.run(scenario()) == 0
    assert harness['calls'] == 1
    assert harness['rows'][-1]['outcome'] == 'stop_requested'


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX supervisor signal contract')
def test_real_process_sigterm_finishes_inflight_cycle_then_exits():
    import signal
    env = {k: v for k, v in os.environ.items() if not k.startswith(('ACQUISITION_', 'SUPABASE_', 'FACEBOOK_'))}
    env['ACQUISITION_FACEBOOK_RUNNER_ENABLED'] = 'true'
    script = '''
import asyncio
from types import SimpleNamespace
from tools import acquisition_facebook_runner as runner
async def synthetic_work():
    await asyncio.sleep(.1)
    return {'status':'idle'}
runner.process_facebook_inquiry=synthetic_work
raise SystemExit(asyncio.run(runner.supervised(SimpleNamespace(max_cycles=3,interval_seconds=30))))
'''
    child = subprocess.Popen([sys.executable, '-u', '-c', script], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        # A bounded pipe wait avoids hanging the test if startup regresses.
        import selectors
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=10), 'Runner did not report startup'
            first = json.loads(child.stdout.readline())
        assert first['event'] == 'cycle_started'
        child.send_signal(signal.SIGTERM)
        stdout, stderr = child.communicate(timeout=10)
        assert child.returncode == 0
        assert stderr == ''
        rows = [json.loads(line) for line in stdout.splitlines()]
        assert [r['event'] for r in rows] == ['cycle_finished', 'stopped']
        assert rows[-1]['outcome'] == 'stop_requested'
    finally:
        if child.poll() is None:
            child.kill(); child.communicate(timeout=5)
