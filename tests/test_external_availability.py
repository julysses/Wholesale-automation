"""Availability alert behavior, including transient failures and safe diagnostics."""
import json
import socket
import ssl
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.error import HTTPError, URLError

import pytest
from scripts import check_launch_availability as monitor


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(monitor, 'sleep', MagicMock())
    monkeypatch.delenv('GITHUB_STEP_SUMMARY', raising=False)


def response(status=200, body=b'{"status":"ok"}'):
    result = MagicMock()
    result.__enter__.return_value = SimpleNamespace(status=status, read=lambda n: body)
    return result


def transport(monkeypatch, outcomes):
    mocked = MagicMock(side_effect=outcomes)
    monkeypatch.setattr(monitor, 'urlopen', mocked)
    return mocked


def probe(name='hilltop_site'):
    return monitor.probe((name, monitor.TARGETS[name]))[1]


@pytest.mark.parametrize('failure,reason', [
    (TimeoutError('private'), 'timeout'),
    (URLError(socket.gaierror(-2, 'private')), 'dns_error'),
    (URLError(ConnectionResetError('private')), 'connection_error'),
    (HTTPError('private', 503, 'private', {}, None), 'http_error'),
])
def test_transient_failure_recovers_without_an_outage_alert(monkeypatch, failure, reason):
    mocked = transport(monkeypatch, [failure, response()])
    result = probe()
    assert result['ok'] is True
    assert [a['reason'] for a in result['attempts']] == [reason, 'ok']
    assert mocked.call_count == 2
    monitor.sleep.assert_called_once_with(2)
    assert mocked.call_args.kwargs['timeout'] == 10
    assert mocked.call_args.args[0].get_method() == 'GET'


def test_repeated_timeout_is_bounded_and_remains_failed(monkeypatch):
    mocked = transport(monkeypatch, [TimeoutError('private')] * 3)
    result = probe()
    assert not result['ok'] and len(result['attempts']) == 3
    assert mocked.call_count == 3
    assert [call.args[0] for call in monitor.sleep.call_args_list] == [2, 5]


@pytest.mark.parametrize('failure,reason', [
    (ssl.SSLCertVerificationError('private'), 'tls_error'),
    (URLError(ssl.SSLCertVerificationError('private')), 'tls_error'),
    (HTTPError('private', 403, 'private', {}, None), 'http_error'),
    (HTTPError('private', 404, 'private', {}, None), 'http_error'),
    (RuntimeError('private'), 'unexpected_error'),
])
def test_permanent_failure_is_not_hidden_by_retry(monkeypatch, failure, reason):
    mocked = transport(monkeypatch, [failure])
    result = probe()
    assert not result['ok'] and len(result['attempts']) == 1
    assert result['attempts'][0]['reason'] == reason
    assert mocked.call_count == 1
    monitor.sleep.assert_not_called()


@pytest.mark.parametrize('body,reason', [
    (b'private not json', 'invalid_readiness_json'),
    (b'\xff', 'invalid_readiness_json'),
    (b'{"status":"unavailable"}', 'readiness_unavailable'),
    (b'[]', 'readiness_unavailable'),
    (b'{}', 'readiness_unavailable'),
])
def test_http_200_does_not_override_invalid_crm_readiness(monkeypatch, body, reason):
    transport(monkeypatch, [response(body=body)])
    result = probe('crm_readiness')
    assert not result['ok'] and result['attempts'][0]['reason'] == reason
    monitor.sleep.assert_not_called()


@pytest.mark.parametrize('name', monitor.TARGETS)
def test_healthy_target_needs_only_one_request(monkeypatch, name):
    mocked = transport(monkeypatch, [response()])
    result = probe(name)
    assert result['ok'] and len(result['attempts']) == 1
    assert mocked.call_count == 1


def test_crm_outage_can_recover_but_must_return_valid_readiness(monkeypatch):
    transport(monkeypatch, [response(503), response(body=b'{}')])
    result = probe('crm_readiness')
    assert not result['ok']
    assert [a['reason'] for a in result['attempts']] == ['http_error', 'readiness_unavailable']


@pytest.mark.parametrize('failed', [True, False])
def test_exit_code_summary_and_annotations_preserve_failures(monkeypatch, tmp_path, capsys, failed):
    summary = tmp_path / 'summary.md'
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(summary))
    def outcome(item):
        bad = failed and item[0] == 'hilltop_site'
        return item[0], {'ok': not bad, 'attempts': [
            {'ok': not bad, 'reason': 'timeout' if bad else 'ok',
             'http_status': None if bad else 200, 'elapsed_ms': 12}]}
    monkeypatch.setattr(monitor, 'probe', outcome)
    assert monitor.main() == (1 if failed else 0)
    captured = capsys.readouterr().out
    assert ('::error title=Availability check failed::hilltop_site' in captured) == failed
    assert json.loads(captured.splitlines()[0])['crm_readiness']['ok']
    assert ('FAILED' in summary.read_text()) == failed
    assert 'SMS delivery' in summary.read_text()


def test_recovered_attempt_is_visible_without_failed_run(monkeypatch, tmp_path, capsys):
    transport(monkeypatch, [URLError(TimeoutError('secret response')), response()])
    result = probe()
    monkeypatch.setenv('GITHUB_STEP_SUMMARY', str(tmp_path / 'summary.md'))
    monitor.report({'hilltop_site': result})
    output = capsys.readouterr().out + (tmp_path / 'summary.md').read_text()
    assert 'recovered after retry' in output and '::notice' in output
    assert 'timeout' in output and 'secret' not in output and '::error' not in output
