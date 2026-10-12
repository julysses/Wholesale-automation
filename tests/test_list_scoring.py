import json
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from tools.list_scoring import score_list_lead, save_score_receipt, ListAssessment, ScoringUnconfirmed

@pytest.fixture
def scoring():
    db, client = MagicMock(), MagicMock()
    lead, evaluation = uuid4(), uuid4()
    component = lambda p: {'points':p,'reason':'Synthetic evidence','evidence_ids':['fixture'] if p else []}
    assessment = {'components':{k:component(v) for k,v in [('distress_stack',7),('need_to_sell',0),('equity',0),('contactability',0),('recency',0)]},'needs_to_sell':'unknown'}
    client.with_options.return_value = client
    client.messages.create.return_value = SimpleNamespace(id='msg-test',model='claude-test',stop_reason='end_turn',content=[SimpleNamespace(type='text',text=json.dumps(assessment))])
    def rpc(name, params):
        if name=='list_scoring_input': value={'input':{'lead_id':str(lead)},'input_hash':'a'*64}
        else: value={'evaluation':{'id':str(evaluation),'lead_id':str(lead),'input_hash':'a'*64,'model_version':'claude-test','prompt_version':'daily-list-score-v1','model_receipt':'msg-test','reasons':assessment,'score':7},'outreach_authorized':False}
        return SimpleNamespace(execute=lambda:SimpleNamespace(data=value))
    db.rpc.side_effect=rpc
    return db,client,evaluation,lead,assessment

def test_disabled_scoring_never_calls_model_or_database(scoring):
    assert score_list_lead(*scoring[:4])=={'blocked':'scoring_disabled'}
    scoring[0].rpc.assert_not_called();scoring[1].messages.create.assert_not_called()

def test_score_uses_current_snapshot_and_validates_saved_identity(scoring):
    assert score_list_lead(*scoring[:4],enabled=True)['evaluation']['score']==7
    scoring[1].with_options.assert_called_once_with(max_retries=0)
    scoring[0].rpc.assert_called_with('save_list_score',{'p_id':str(scoring[2]),'p_lead':str(scoring[3]),'p_input_hash':'a'*64,'p_model':'claude-test','p_prompt':'daily-list-score-v1','p_receipt':'msg-test','p_result':scoring[4]})

@pytest.mark.parametrize('text',['not JSON','{"components":{},"needs_to_sell":"confirmed"}'])
def test_malformed_response_never_saves(scoring,text):
    scoring[1].messages.create.return_value.content[0].text=text
    with pytest.raises(ValueError):score_list_lead(*scoring[:4],enabled=True)
    assert scoring[0].rpc.call_count==1

def test_truncation_never_saves(scoring):
    scoring[1].messages.create.return_value.stop_reason='max_tokens'
    with pytest.raises(ScoringUnconfirmed):score_list_lead(*scoring[:4],enabled=True)
    assert scoring[0].rpc.call_count==1

def test_lost_save_acknowledgement_preserves_exact_receipt_for_model_free_retry(scoring):
    db,client,evaluation,lead,assessment=scoring
    original=db.rpc.side_effect
    def lost(name,params):
        if name=='save_list_score':raise TimeoutError('lost acknowledgement')
        return original(name,params)
    db.rpc.side_effect=lost
    with pytest.raises(ScoringUnconfirmed) as error:score_list_lead(*scoring[:4],enabled=True)
    pending=error.value.pending_save
    assert pending['p_id']==str(evaluation) and pending['p_result']==assessment
    db.rpc.side_effect=original
    save_score_receipt(db,evaluation,lead,pending['p_input_hash'],pending['p_model'],pending['p_receipt'],ListAssessment.model_validate(pending['p_result']))
    client.messages.create.assert_called_once()
