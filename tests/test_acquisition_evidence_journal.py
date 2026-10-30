"""Restart and uncertain-write recovery with synthetic signed observations."""
import asyncio
import copy
import json
import os
import sqlite3
from uuid import uuid4

import httpx
import pytest

from tests.test_acquisition_evidence import ARTIFACT, AUTH, CAMPAIGN, WORKSPACE, Stream
from tests.test_acquisition_evidence_attestation import ACTOR, REQUEST, sign
from tests.test_acquisition_evidence_persistence import receipt
from tools.acquisition_evidence_journal import EvidenceJournal, EvidenceJournalUnavailable
from tools.acquisition_store import AcquisitionStore
from tools.acquisition_evidence_persistence import EvidencePersistenceUnconfirmed

SCOPE=dict(workspace_id=WORKSPACE,campaign_id=CAMPAIGN,artifact_id=ARTIFACT,actor_id=ACTOR,session_id=ACTOR)


def journal(tmp_path):
    path=tmp_path/'private';path.mkdir(mode=0o700)
    return EvidenceJournal(path)


def run(saved, handler, **scope):
    async def execute():
        async with httpx.AsyncClient(base_url='https://storage.example.test/rest/v1/',headers=AUTH,
                                    transport=httpx.MockTransport(handler)) as client:
            return await AcquisitionStore(client).persist_journaled_evidence(saved,REQUEST,**(SCOPE|scope))
    return asyncio.run(execute())


def success(request):
    return httpx.Response(200,stream=Stream([json.dumps(receipt(duplicate=True)).encode()]),headers={'content-type':'application/json'})


def test_restart_retains_original_signed_text_and_reconciles_lost_reply(tmp_path):
    saved=journal(tmp_path);original=sign();saved.prepare(original);calls=[]
    def lost(request):
        calls.append(request.content)
        assert saved.load(REQUEST)[1]=='unconfirmed'
        raise httpx.ReadError('synthetic lost committed reply')
    with pytest.raises(EvidencePersistenceUnconfirmed):run(saved,lost)
    restarted=EvidenceJournal(saved.directory)
    body,state=restarted.load(REQUEST)
    assert body==original and state=='unconfirmed'
    def retry(request):
        calls.append(request.content)
        return success(request)
    assert run(restarted,retry)['duplicate'] is True
    assert calls[0]==calls[1]
    assert restarted.load(REQUEST)==(original,'confirmed')
    assert os.stat(saved.path).st_mode & 0o077 == 0


def test_restart_after_mark_before_network_remains_recoverable(tmp_path):
    saved=journal(tmp_path);body=sign();saved.prepare(body);saved.mark_dispatch(REQUEST,body,'https://storage.example.test/rest/v1/')
    restarted=EvidenceJournal(saved.directory)
    assert restarted.load(REQUEST)==(body,'unconfirmed')
    assert run(restarted,success)['execution_authorized'] is False


def test_same_identity_never_replaces_original_payload(tmp_path):
    saved=journal(tmp_path);body=sign();saved.prepare(body)
    saved.prepare(dict(reversed(list(body.items()))))
    changed=copy.deepcopy(body);changed['p_signature']='0'*64
    with pytest.raises(EvidenceJournalUnavailable):saved.prepare(changed)
    assert saved.load(REQUEST)==(body,'prepared')


def test_scope_mismatch_does_not_dispatch_or_change_state(tmp_path):
    saved=journal(tmp_path);saved.prepare(sign());calls=[]
    with pytest.raises(EvidenceJournalUnavailable):run(saved,lambda request:calls.append(request),workspace_id=uuid4())
    assert not calls and saved.load(REQUEST)[1]=='prepared'


def test_failed_confirmation_retains_exact_request(tmp_path,monkeypatch):
    saved=journal(tmp_path);body=sign();saved.prepare(body)
    def fail(*args):raise sqlite3.OperationalError('synthetic disk full')
    monkeypatch.setattr(saved,'confirm',fail)
    with pytest.raises(EvidencePersistenceUnconfirmed):run(saved,success)
    assert EvidenceJournal(saved.directory).load(REQUEST)==(body,'unconfirmed')


def test_failed_pre_dispatch_commit_sends_nothing(tmp_path,monkeypatch):
    saved=journal(tmp_path);saved.prepare(sign());calls=[]
    def fail(*args):raise sqlite3.OperationalError('synthetic disk full')
    monkeypatch.setattr(saved,'mark_dispatch',fail)
    with pytest.raises(sqlite3.OperationalError):run(saved,lambda req:calls.append(req))
    assert not calls


def test_confirmed_history_is_rechecked_not_used_as_current_authority(tmp_path):
    saved=journal(tmp_path);saved.prepare(sign());run(saved,success);calls=[]
    def denied(request):calls.append(request);return httpx.Response(403)
    with pytest.raises(EvidencePersistenceUnconfirmed):run(saved,denied)
    assert len(calls)==1 and saved.load(REQUEST)[1]=='unconfirmed'


@pytest.mark.parametrize('kind',['directory_mode','directory_link','file_mode','file_link','hard_link'])
def test_refuses_nonprivate_or_linked_journal(tmp_path,kind):
    saved=journal(tmp_path)
    if kind=='directory_mode':saved.directory.chmod(0o755)
    elif kind=='directory_link':
        link=tmp_path/'alias';link.symlink_to(saved.directory,target_is_directory=True)
        with pytest.raises(EvidenceJournalUnavailable):EvidenceJournal(link)
        return
    elif kind=='file_mode':saved.path.chmod(0o644)
    elif kind=='file_link':
        saved.path.unlink();saved.path.symlink_to(tmp_path/'other')
    else:os.link(saved.path,tmp_path/'alias')
    with pytest.raises(EvidenceJournalUnavailable):EvidenceJournal(saved.directory)


def test_concurrent_preparation_converges_and_rejects_changed_request(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    saved=journal(tmp_path);body=sign()
    other=EvidenceJournal(saved.directory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda j:j.prepare(body),[saved,other]))
    assert results==[REQUEST,REQUEST]
    changed=copy.deepcopy(body);changed['p_actor']=str(uuid4())
    with pytest.raises(EvidenceJournalUnavailable):other.prepare(changed)
    assert saved.load(REQUEST)==(body,'prepared')


def test_invalid_signed_request_is_not_saved_or_exposed_in_error(tmp_path):
    saved=journal(tmp_path);body=sign();body['p_signature']='private-invalid-value'
    with pytest.raises(EvidenceJournalUnavailable) as error:saved.prepare(body)
    assert 'private-invalid-value' not in str(error.value)
    with pytest.raises(EvidenceJournalUnavailable):saved.load(REQUEST)


def test_worker_process_exit_after_dispatch_marker_preserves_recovery(tmp_path):
    import subprocess
    import sys
    saved=journal(tmp_path);saved.prepare(sign())
    code='''
import os,sys
from pathlib import Path
from uuid import UUID
from tools.acquisition_evidence_journal import EvidenceJournal
j=EvidenceJournal(Path(sys.argv[1]));identity=UUID(sys.argv[2])
body,_=j.load(identity);j.mark_dispatch(identity,body,'https://storage.example.test/rest/v1/')
os._exit(0)
'''
    result=subprocess.run([sys.executable,'-c',code,str(saved.directory),str(REQUEST)],timeout=10,capture_output=True)
    assert result.returncode==0,result.stderr.decode()
    restarted=EvidenceJournal(saved.directory)
    assert restarted.load(REQUEST)==(sign(),'unconfirmed')
    assert run(restarted,success)['duplicate'] is True


def test_restart_discovers_pending_requests_without_retained_ids(tmp_path):
    saved=journal(tmp_path);body=sign();saved.prepare(body)
    changed=copy.deepcopy(body);changed['p_id']='ffffffff-ffff-4fff-8fff-ffffffffffff'
    saved.prepare(changed);saved.mark_dispatch(REQUEST,body,'https://storage.example.test/rest/v1/')
    reopened=EvidenceJournal(saved.directory)
    first=reopened.pending(workspace_id=WORKSPACE,actor_id=ACTOR,limit=1)
    assert first['items']==[{'id':str(REQUEST),'campaign_id':str(CAMPAIGN),
        'artifact_id':str(ARTIFACT),'session_id':str(ACTOR),'state':'unconfirmed'}]
    assert first['next_after']==str(REQUEST)
    from uuid import UUID
    second=reopened.pending(workspace_id=WORKSPACE,actor_id=ACTOR,after=UUID(first['next_after']),limit=1)
    assert second['items'][0]['id']==changed['p_id'] and second['next_after'] is None
    assert 'p_signature' not in json.dumps(first) and 'p_observation' not in json.dumps(first)
    assert reopened.load(REQUEST)==(body,'unconfirmed')


def test_pending_discovery_is_scoped_and_excludes_confirmed(tmp_path):
    saved=journal(tmp_path);saved.prepare(sign());run(saved,success)
    other_workspace=uuid4();other_actor=uuid4()
    body=sign();body['p_id']=str(uuid4());body['p_workspace']=str(other_workspace);saved.prepare(body)
    second=sign();second['p_id']=str(uuid4());second['p_actor']=str(other_actor);saved.prepare(second)
    assert saved.pending(workspace_id=WORKSPACE,actor_id=ACTOR)=={'items':[],'next_after':None}
    assert len(saved.pending(workspace_id=other_workspace,actor_id=ACTOR)['items'])==1
    assert len(saved.pending(workspace_id=WORKSPACE,actor_id=other_actor)['items'])==1


@pytest.mark.parametrize('change',[{'limit':0},{'limit':101},{'limit':True},{'limit':1.5},
    {'workspace_id':str(WORKSPACE)},{'actor_id':None},{'after':'bad'}])
def test_pending_rejects_invalid_scope_and_bounds(tmp_path,change):
    saved=journal(tmp_path)
    with pytest.raises(EvidenceJournalUnavailable):saved.pending(**(dict(workspace_id=WORKSPACE,actor_id=ACTOR)|change))


def test_pending_fails_closed_on_corrupt_record(tmp_path):
    saved=journal(tmp_path);body=sign();saved.prepare(body)
    body['p_signature']='private-invalid-signature'
    with sqlite3.connect(saved.path) as db:db.execute('UPDATE requests SET body=?',(json.dumps(body),))
    with pytest.raises(EvidenceJournalUnavailable) as error:saved.pending(workspace_id=WORKSPACE,actor_id=ACTOR)
    assert 'private-invalid-signature' not in str(error.value)


def test_old_journal_without_recovery_index_opens_without_losing_requests(tmp_path):
    saved=journal(tmp_path);body=sign();saved.prepare(body)
    with sqlite3.connect(saved.path) as db:db.execute('DROP INDEX pending_observation_scope')
    reopened=EvidenceJournal(saved.directory)
    assert reopened.load(REQUEST)==(body,'prepared')
    assert reopened.pending(workspace_id=WORKSPACE,actor_id=ACTOR)['items'][0]['id']==str(REQUEST)


def test_capacity_holds_new_work_without_erasing_exact_recovery(tmp_path,monkeypatch):
    monkeypatch.setattr('tools.acquisition_evidence_journal.MAX_JOURNAL_REQUESTS',1)
    saved=journal(tmp_path);body=sign();saved.prepare(body);saved.mark_dispatch(REQUEST,body,'https://storage.example.test/rest/v1/')
    new=copy.deepcopy(body);new['p_id']=str(uuid4())
    with pytest.raises(EvidenceJournalUnavailable,match='capacity'):saved.prepare(new)
    assert saved.prepare(body)==REQUEST
    assert saved.load(REQUEST)==(body,'unconfirmed')
    assert run(saved,success)['duplicate'] is True
    # Even confirmed history is retained; no automatic purge or quota bypass.
    with pytest.raises(EvidenceJournalUnavailable,match='capacity'):saved.prepare(new)
    assert saved.prepare(body)==REQUEST
    assert saved.load(REQUEST)[1]=='confirmed'


def test_concurrent_admission_cannot_overfill_journal(tmp_path,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    monkeypatch.setattr('tools.acquisition_evidence_journal.MAX_JOURNAL_REQUESTS',1)
    saved=journal(tmp_path);other=EvidenceJournal(saved.directory)
    first=sign();second=copy.deepcopy(first);second['p_id']=str(uuid4())
    def attempt(pair):
        store,body=pair
        try:return store.prepare(body)
        except EvidenceJournalUnavailable:return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(attempt,[(saved,first),(other,second)]))
    assert sum(value is not None for value in result)==1
    assert len(saved.pending(workspace_id=WORKSPACE,actor_id=ACTOR)['items'])==1


def test_recovery_refuses_different_destination_before_network(tmp_path):
    saved=journal(tmp_path);body=sign();saved.prepare(body)
    saved.mark_dispatch(REQUEST,body,'https://storage.example.test/rest/v1/')
    calls=[]
    async def attempt():
        async with httpx.AsyncClient(base_url='https://other.example.test/rest/v1/',headers=AUTH,
            transport=httpx.MockTransport(lambda request:calls.append(request))) as client:
            await AcquisitionStore(client).persist_journaled_evidence(saved,REQUEST,**SCOPE)
    with pytest.raises(EvidenceJournalUnavailable,match='Original journal destination'):asyncio.run(attempt())
    assert not calls and saved.load(REQUEST)==(body,'unconfirmed')
    assert run(saved,success)['duplicate'] is True


def test_legacy_dispatched_request_without_destination_requires_review(tmp_path):
    saved=journal(tmp_path);body=sign();saved.prepare(body)
    with sqlite3.connect(saved.path) as db:
        db.execute("UPDATE requests SET state='unconfirmed',destination=NULL")
    reopened=EvidenceJournal(saved.directory);calls=[]
    with pytest.raises(EvidenceJournalUnavailable,match='recovery review'):
        run(reopened,lambda request:calls.append(request))
    assert not calls and reopened.load(REQUEST)==(body,'unconfirmed')
    assert reopened.pending(workspace_id=WORKSPACE,actor_id=ACTOR)['items'][0]['id']==str(REQUEST)


def test_additive_destination_upgrade_preserves_old_prepared_request(tmp_path):
    saved=journal(tmp_path);body=sign();saved.prepare(body)
    with sqlite3.connect(saved.path) as db:db.execute('ALTER TABLE requests DROP COLUMN destination')
    reopened=EvidenceJournal(saved.directory)
    assert reopened.load(REQUEST)==(body,'prepared')
    assert run(reopened,success)['duplicate'] is True


def test_concurrent_first_dispatch_cannot_bind_two_destinations(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    saved=journal(tmp_path);body=sign();saved.prepare(body)
    other=EvidenceJournal(saved.directory)
    def bind(pair):
        store,origin=pair
        try:store.mark_dispatch(REQUEST,body,origin);return origin
        except EvidenceJournalUnavailable:return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        result=list(pool.map(bind,[(saved,'https://storage.example.test/rest/v1/'),
                                   (other,'https://other.example.test/rest/v1/')]))
    assert sum(value is not None for value in result)==1
    with sqlite3.connect(saved.path) as db:
        destination=db.execute('SELECT destination FROM requests').fetchone()[0]
    assert destination==next(value for value in result if value is not None)
    assert saved.load(REQUEST)==(body,'unconfirmed')
