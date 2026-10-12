"""A configured provider key must not bypass durable trace accounting."""
from unittest.mock import patch

from config.settings import settings
from orchestrator import MasterOrchestrator
from schemas.property import DataSource, NormalizedAddress, PropertyLead
from tools.batchdata_adapter import BatchDataAdapter, SkipTracePayload


def test_direct_and_batch_tracing_cannot_purchase_without_ledger(monkeypatch):
    monkeypatch.setattr(settings, 'batchdata_api_key', 'synthetic-not-a-key')
    adapter = BatchDataAdapter()
    payload = SkipTracePayload('Synthetic', 'TEST ONLY', 'Dallas')
    with patch('tools.batchdata_adapter.httpx.Client') as network:
        direct = adapter.skip_trace_property(payload, 'fixture-one')
        batch = adapter.skip_trace_batch([('fixture-two', payload), ('fixture-three', payload)])
    network.assert_not_called()
    assert [r.lead_id for r in [direct, *batch]] == ['fixture-one', 'fixture-two', 'fixture-three']
    for result in [direct, *batch]:
        assert not result.success
        assert result.error.startswith('blocked:')
        assert result.phones == [] and result.emails == []


def test_orchestrator_reports_block_and_preserves_existing_contact(monkeypatch):
    monkeypatch.setattr(settings, 'batchdata_api_key', 'synthetic-not-a-key')
    monkeypatch.setattr(settings, 'auto_skip_trace', True)
    lead = PropertyLead(
        address=NormalizedAddress(street='TEST ONLY', city='Dallas', state='TX', zip_code='75201'),
        owner_name='Synthetic', source=DataSource.TAX_DELINQUENT,
        phone_numbers=['+12145550198'],
    )
    with patch('agents.base_agent.anthropic.Anthropic'), patch('tools.batchdata_adapter.httpx.Client') as network:
        orchestrator = MasterOrchestrator()
        with patch.object(orchestrator.compliance, 'log_action') as audit:
            result = orchestrator.skip_trace_leads([lead])
    network.assert_not_called()
    assert not result[str(lead.id)].success
    assert lead.phone_numbers == ['+12145550198']
    assert orchestrator.state.skip_trace_results[str(lead.id)].error.startswith('blocked:')
    assert 'blocked=1' in audit.call_args.kwargs['output_summary']
