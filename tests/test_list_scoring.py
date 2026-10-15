import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from config.settings import settings
from tools.list_scoring import score_list_lead, receive_score_receipt, ScoringUnconfirmed

@pytest.fixture
def scoring(monkeypatch):
    db, client = MagicMock(), MagicMock()
    lead, evaluation = uuid4(), uuid4()
    component = lambda p: {'points':p,'reason':'Synthetic evidence','evidence_ids':['fixture'] if p else []}
    assessment = {'components':{k:component(v) for k,v in [('distress_stack',7),('need_to_sell',0),('equity',0),('contactability',0),('recency',0)]},'needs_to_sell':'unknown'}
    row = {'id':str(evaluation),'lead_id':str(lead),'input_hash':'a'*64,'input_snapshot':{'lead_id':str(lead)},'requested_model':settings.claude_model,'prompt_version':'daily-list-score-v1','state':'queued','claim_token':None}
    failures = {}
    client.with_options.return_value = client
    client.messages.create.return_value = SimpleNamespace(id='msg-test',model=settings.claude_model,stop_reason='end_turn',content=[SimpleNamespace(type='text',text=json.dumps(assessment))])
    def rpc(name, params):
        def execute():
            if name=='prepare_list_score_job': value={'job':deepcopy(row)}
            elif name=='claim_list_score_job':
                dispatch=row['state']=='queued'
                if dispatch:row.update(state='submitted',claim_token=str(uuid4()))
                value={'job':deepcopy(row),'dispatch':dispatch}
            elif name=='receive_list_score_job':
                row.update(state='received',model_version=params['p_model'],model_receipt=params['p_receipt'],assessment=params['p_result'])
                value={'job':deepcopy(row)}
            elif name=='complete_list_score_job':
                row.update(state='completed')
                value={'job':deepcopy(row),'evaluation':{'id':str(evaluation),'lead_id':str(lead),'input_hash':'a'*64,'model_version':settings.claude_model,'prompt_version':'daily-list-score-v1','model_receipt':'msg-test','reasons':assessment,'score':7},'outreach_authorized':False}
            else:raise AssertionError(name)
            if failures.get(name):raise TimeoutError('lost acknowledgement')
            return SimpleNamespace(data=value)
        return SimpleNamespace(execute=execute)
    db.rpc.side_effect=rpc
    monkeypatch.setattr('tools.operational_alerts.record_provider_alert',MagicMock())
    return db,client,evaluation,lead,assessment,row,failures

def run(f):return score_list_lead(*f[:4],enabled=True)

def test_disabled_scoring_never_calls_model_or_database(scoring):
    assert score_list_lead(*scoring[:4])=={'blocked':'scoring_disabled'}
    scoring[0].rpc.assert_not_called();scoring[1].messages.create.assert_not_called()

def test_score_uses_claim_and_completed_retry_never_calls_model_again(scoring):
    assert run(scoring)['evaluation']['score']==7
    assert run(scoring)['evaluation']['score']==7
    scoring[1].with_options.assert_called_once_with(max_retries=0)
    scoring[1].messages.create.assert_called_once()

@pytest.mark.parametrize('text',['not JSON','{"components":{},"needs_to_sell":"confirmed"}'])
def test_malformed_response_never_saves_or_retries_model(scoring,text):
    scoring[1].messages.create.return_value.content[0].text=text
    with pytest.raises(ScoringUnconfirmed):run(scoring)
    assert scoring[5]['state']=='submitted'
    assert run(scoring)['dispatch'] is False
    scoring[1].messages.create.assert_called_once()

def test_truncation_never_saves(scoring):
    scoring[1].messages.create.return_value.stop_reason='max_tokens'
    with pytest.raises(ScoringUnconfirmed):run(scoring)
    assert scoring[5]['state']=='submitted'

def test_lost_claim_ack_cannot_authorize_model(scoring):
    scoring[6]['claim_list_score_job']=True
    with pytest.raises(ScoringUnconfirmed):run(scoring)
    assert run(scoring)['dispatch'] is False
    scoring[1].messages.create.assert_not_called()

def test_lost_receipt_ack_resumes_saved_response_without_model(scoring):
    scoring[6]['receive_list_score_job']=True
    with pytest.raises(ScoringUnconfirmed) as error:run(scoring)
    assert error.value.pending_save['p_result']==scoring[4]
    assert scoring[5]['state']=='received'
    assert run(scoring)['evaluation']['score']==7
    scoring[1].messages.create.assert_called_once()

def test_lost_completion_ack_recovers_completed_job(scoring):
    scoring[6]['complete_list_score_job']=True
    with pytest.raises(ScoringUnconfirmed):run(scoring)
    scoring[6].clear()
    assert run(scoring)['evaluation']['score']==7
    scoring[1].messages.create.assert_called_once()

def test_provider_timeout_is_not_resubmitted(scoring):
    scoring[1].messages.create.side_effect=TimeoutError('uncertain')
    with pytest.raises(ScoringUnconfirmed):run(scoring)
    assert run(scoring)['dispatch'] is False
    scoring[1].messages.create.assert_called_once()

def test_model_identity_mismatch_cannot_persist(scoring):
    scoring[1].messages.create.return_value.model='different-model'
    with pytest.raises(ScoringUnconfirmed):run(scoring)
    assert scoring[5]['state']=='submitted'
