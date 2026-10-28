"""Same provider-schema examples must satisfy the real preparation boundary."""
import json
from pathlib import Path

import pytest
from tools.acquisition_inbound_tools import prepare_inbound_tool
from tools.acquisition_intake import FIELDS
from tests.test_acquisition_inbound_tools import ROUTE, payload

ROOT=Path(__file__).resolve().parents[1]/'config/acquisition/inbound'
CASES=json.loads((ROOT/'tool-contract-cases.json').read_text())


@pytest.mark.parametrize('scenario',CASES,ids=[case['id'] for case in CASES])
def test_review_config_examples_against_server(scenario):
    data=payload();data.update(name=scenario['name'],args=scenario['args'])
    if not scenario['valid']:
        with pytest.raises(ValueError): prepare_inbound_tool(data,**ROUTE)
    else:
        result=prepare_inbound_tool(data,**ROUTE)
        assert result['execution_authorized'] is False
        if scenario['id']=='ambiguous_price_preserved':
            assert result['prepared']['asking_price'] is None
        assert 'PRIVATE TRANSCRIPT' not in str(result)


def test_draft_answer_fields_match_server_allowlist():
    tools=json.loads((ROOT/'tools.draft.json').read_text())
    intake=next(tool for tool in tools if tool['name']=='submit_seller_intake')
    assert set(intake['parameters']['properties']['answers']['properties'])==FIELDS


def test_native_termination_is_not_a_database_tool():
    controls=json.loads((ROOT/'controls.draft.json').read_text())
    assert len(controls)==1
    assert set(controls[0])=={'type','name','description'}
    assert controls[0]['type']==controls[0]['name']=='end_call'
    data=payload();data.update(name='end_call',args={})
    with pytest.raises(ValueError):
        prepare_inbound_tool(data,**ROUTE)
