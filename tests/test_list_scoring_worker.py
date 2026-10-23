from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from tools import list_scoring_worker as worker
from tests.test_daily_list_launch_guards import client

def job(state='queued',model='model-fixture'):
    return {'id':str(uuid4()),'lead_id':str(uuid4()),'state':state,'requested_model':model}

def database(jobs):
    db=MagicMock();db.rpc.return_value.execute.return_value=SimpleNamespace(data={'jobs':jobs});return db

def test_disabled_worker_does_not_read_jobs_or_construct_provider(monkeypatch):
    monkeypatch.delenv('LIST_SCORING_ENABLED',raising=False);db=MagicMock()
    assert worker.process_scoring_batch(db=db)['status']=='disabled';db.rpc.assert_not_called()

@pytest.mark.parametrize('value',['bad','0','11'])
def test_invalid_batch_fails_before_database(monkeypatch,value):
    monkeypatch.setenv('LIST_SCORING_ENABLED','true');monkeypatch.setenv('LIST_SCORING_BATCH_SIZE',value);db=MagicMock()
    with pytest.raises(RuntimeError):worker.process_scoring_batch(db=db)
    db.rpc.assert_not_called()

def test_received_response_finishes_without_api_credentials(monkeypatch):
    monkeypatch.setenv('LIST_SCORING_ENABLED','true');monkeypatch.setattr(worker.settings,'anthropic_api_key','')
    entry=job('received','prior-model');db=database([entry])
    score=MagicMock(return_value={'job':{'state':'completed'}});monkeypatch.setattr(worker,'score_list_lead',score)
    assert worker.process_scoring_batch(db=db)['completed']==1
    assert score.call_args.args[1] is None
    assert score.call_args.kwargs['model']=='prior-model'

def test_missing_key_keeps_queued_job_without_dispatch(monkeypatch):
    monkeypatch.setenv('LIST_SCORING_ENABLED','true');monkeypatch.setattr(worker.settings,'anthropic_api_key','')
    db=database([job()]);score=MagicMock();monkeypatch.setattr(worker,'score_list_lead',score)
    assert worker.process_scoring_batch(db=db)['outcomes'][0]['blocked']=='model_not_configured';score.assert_not_called()

def test_time_budget_defers_remaining_jobs_without_losing_references(monkeypatch):
    monkeypatch.setenv('LIST_SCORING_ENABLED','true');entries=[job(),job()];db=database(entries)
    score=MagicMock(return_value={'job':{'state':'completed'}});monkeypatch.setattr(worker,'score_list_lead',score)
    ticks=iter([0,0,41]);result=worker.process_scoring_batch(db=db,client=MagicMock(),clock=lambda:next(ticks))
    assert result['completed']==1 and result['deferred']==1
    assert result['outcomes'][0]['job_id']==entries[0]['id'];score.assert_called_once()

def test_bad_selection_never_processes_part_of_a_batch(monkeypatch):
    monkeypatch.setenv('LIST_SCORING_ENABLED','true');entry=job();db=database([entry,entry]);score=MagicMock();monkeypatch.setattr(worker,'score_list_lead',score)
    with pytest.raises(RuntimeError,match='Duplicate'):worker.process_scoring_batch(db=db,client=MagicMock())
    score.assert_not_called()

def test_worker_route_checks_secret_before_any_processing(client,monkeypatch):
    process=MagicMock(return_value={'status':'disabled'});monkeypatch.setattr(worker,'process_scoring_batch',process)
    path='/webhooks/_worker/list-scoring';monkeypatch.delenv('CRON_SECRET',raising=False)
    assert client.get(path).status_code==503
    monkeypatch.setenv('CRON_SECRET','synthetic-worker-secret')
    assert client.get(path,headers={'Authorization':'Bearer wrong'}).status_code==401;process.assert_not_called()
    assert client.get(path,headers={'Authorization':'Bearer synthetic-worker-secret'}).status_code==200;process.assert_called_once()
