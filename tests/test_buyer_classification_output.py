"""No provider access: validate classification and bound its SDK attempt."""
import json
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from agents.buyer_intelligence_agent import BuyerIntelligenceAgent, InvalidBuyerClassification


def agent_output(value):
    agent=object.__new__(BuyerIntelligenceAgent)
    agent._call_claude=Mock(return_value=value)
    return agent


@pytest.mark.parametrize('field,value', [('buyer_type','other'),('confidence',float('nan')),('confidence',1.1),('confidence','0.9'),('reasoning',''),('suggested_tags',['']),('suggested_tags',['x'*81])])
def test_invalid_model_output_never_invents_landlord(field,value):
    data={'buyer_type':'builder','confidence':0.9,'reasoning':'Synthetic reason','suggested_tags':[]}
    data[field]=value
    with pytest.raises(InvalidBuyerClassification):agent_output(json.dumps(data)).classify_buyer({'id':'fixture'},[])


def test_missing_and_extra_fields_rejected():
    for data in [{}, {'buyer_type':'landlord','confidence':0.7,'reasoning':'test','suggested_tags':[],'verified':True}]:
        with pytest.raises(InvalidBuyerClassification):agent_output(json.dumps(data)).classify_buyer({},[])


def test_single_attempt_uses_initialized_client_without_settings_attribute():
    agent=object.__new__(BuyerIntelligenceAgent)
    configured=Mock();configured.messages.create.return_value=SimpleNamespace(id='fixture',content=[SimpleNamespace(text='{}')])
    agent._client=Mock();agent._client.with_options.return_value=configured
    assert agent._call_claude('test','test')=='{}'
    agent._client.with_options.assert_called_once_with(timeout=20.0,max_retries=0)
    assert configured.messages.create.call_count==1
    assert agent._last_message_id=='fixture'
