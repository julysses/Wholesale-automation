"""Exact contract observation recovery with synthetic HTTP and private local journal."""
import asyncio
import copy
import json

import httpx
import pytest

from tests.test_acquisition_contract_attestation import sign
from tests.test_acquisition_contract_documents import uid
from tests.test_acquisition_evidence import AUTH, Stream
from tools.acquisition_evidence import EvidenceUnavailable
from tools.acquisition_evidence_persistence import EvidencePersistenceUnconfirmed
from tools.acquisition_evidence_journal import EvidenceJournal, EvidenceJournalUnavailable, persist_journaled_contract_observation
from tools.acquisition_store import AcquisitionStore

SCOPE = dict(workspace_id=uid(2), contract_id=uid(3), contract_version=2, purpose='purchase_contract',
             artifact_id=uid(1), actor_id=uid(5), session_id=uid(6))


def receipt(**changes):
    return dict(verification_id=str(uid(4)), workspace_id=str(uid(2)), contract_id=str(uid(3)),
        contract_version=2, purpose='purchase_contract', artifact_id=str(uid(1)), scan_status='no_detection',
        duplicate=False, observation_persisted=True, preview_authorized=False, legal_review_approved=False,
        execution_authorized=False) | changes


def setup(*, request=None, scope=None, result=None, status=200, headers=None, body=None, error=None,
          origin='https://storage.example.test/rest/v1/', auth=None, journal=None, stream=None):
    request = sign() if request is None else request
    calls = []
    stream = stream or Stream([body if body is not None else json.dumps(receipt() if result is None else result).encode()])
    def handle(req):
        calls.append(req)
        if journal: assert journal.load(uid(4))[1] == 'unconfirmed'
        if error: raise error
        return httpx.Response(status, stream=stream, headers={'content-type':'application/json', **(headers or {})})
    async def execute():
        async with httpx.AsyncClient(base_url=origin, headers=AUTH if auth is None else auth,
                transport=httpx.MockTransport(handle), follow_redirects=True) as client:
            if journal:
                return await AcquisitionStore(client).persist_journaled_contract_observation(journal, uid(4), **(SCOPE | (scope or {})))
            return await AcquisitionStore(client).persist_contract_attestation(request, **(SCOPE | (scope or {})))
    return execute, calls, stream


def test_exact_request_single_fixed_rpc_and_historical_receipt():
    request = sign(); saved = copy.deepcopy(request)
    execute, calls, stream = setup(request=request, result=receipt(duplicate=True))
    assert asyncio.run(execute()) == receipt(duplicate=True)
    assert len(calls) == 1 and stream.closed and request == saved
    assert calls[0].url.path == '/rest/v1/rpc/record_contract_document_verification'
    assert json.loads(calls[0].content) == saved
    assert calls[0].headers['authorization'] == AUTH['Authorization']


@pytest.mark.parametrize('change', [{field:uid(99)} for field in ('workspace_id','contract_id','artifact_id','actor_id','session_id')]
    + [{'contract_version':3}, {'contract_version':True}, {'contract_version':'2'}, {'purpose':'title_report'}])
def test_scope_mismatch_before_dispatch(change):
    execute, calls, _ = setup(scope=change)
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert not calls


@pytest.mark.parametrize('change', [{'p_contract':'BAD'}, {'p_version':True}, {'p_version':'2'}, {'p_version':0},
    {'p_version':2147483648}, {'p_purpose':'mail_content'}, {'p_campaign':str(uid(3))}, {'p_signature':'A'*64},
    {'p_observation':'{}'}, {'p_observation':'{"scan_status":"detected","scan_status":"no_detection"}'},
    {'p_actor':True}, {'p_key':None}])
def test_invalid_signed_envelope_never_sent(change):
    execute, calls, _ = setup(request=sign() | change)
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert not calls


@pytest.mark.parametrize('change', [{'contract_id':str(uid(99))}, {'contract_version':3}, {'contract_version':True},
    {'purpose':'title_report'}, {'workspace_id':str(uid(99))}, {'artifact_id':str(uid(99))},
    {'verification_id':str(uid(99))}, {'scan_status':'detected'}, {'preview_authorized':True},
    {'legal_review_approved':True}, {'execution_authorized':True}, {'observation_persisted':False},
    {'duplicate':1}, {'object_url':'https://private.test/file'}, {'content_approved':False}])
def test_wrong_or_approving_receipt_stays_unconfirmed(change):
    execute, calls, stream = setup(result=receipt(**change))
    with pytest.raises(EvidencePersistenceUnconfirmed): asyncio.run(execute())
    assert len(calls) == 1 and stream.closed


@pytest.mark.parametrize('status', [201,204,206,301,302,307,308,400,401,403,409,422,429,500,503])
def test_failure_does_not_redirect_retry_or_clear_recovery(status):
    execute, calls, stream = setup(status=status, headers={'location':'https://outside.test'})
    with pytest.raises(EvidencePersistenceUnconfirmed): asyncio.run(execute())
    assert len(calls)==1 and stream.closed and stream.reads==0


@pytest.mark.parametrize('body', [b'x'*2049,b'{',b'[]',b'null',b'\xff',
    json.dumps(receipt()).encode()[:-1]+b',"duplicate":true}'])
def test_bad_response_keeps_unknown_state(body):
    execute, _, stream = setup(body=body)
    with pytest.raises(EvidencePersistenceUnconfirmed): asyncio.run(execute())
    assert stream.closed


@pytest.mark.parametrize('headers', [{'content-type':'text/html'}, {'content-encoding':'gzip'},
    {'content-length':'2049'}, {'content-length':'0'}, {'content-length':'1, 2'}])
def test_invalid_headers_rejected_unread(headers):
    execute, _, stream = setup(headers=headers)
    with pytest.raises(EvidencePersistenceUnconfirmed): asyncio.run(execute())
    assert stream.closed and stream.reads==0


@pytest.mark.parametrize('options', [{'origin':'http://storage.example.test/rest/v1/'},
    {'origin':'https://user:secret@storage.example.test/rest/v1/'}, {'origin':'https://storage.example.test/other/'},
    {'origin':'https://storage.example.test/rest/v1/?redirect=evil'}, {'auth':{}},
    {'auth':{'Authorization':'Basic token','apikey':'public'}}])
def test_invalid_destination_or_user_auth_never_sent(options):
    execute, calls, _ = setup(**options)
    with pytest.raises(EvidenceUnavailable): asyncio.run(execute())
    assert not calls


def test_journal_restart_reconciles_lost_reply_exactly_and_binds_destination(tmp_path):
    tmp_path.chmod(0o700); journal=EvidenceJournal(tmp_path)
    request=sign(); journal.prepare(request)
    execute, first, _ = setup(journal=journal, error=httpx.ReadTimeout('lost committed reply'))
    with pytest.raises(EvidencePersistenceUnconfirmed): asyncio.run(execute())
    reopened=EvidenceJournal(tmp_path)
    assert reopened.load(uid(4))==(request,'unconfirmed')
    pending=reopened.pending(workspace_id=uid(2),actor_id=uid(5))['items']
    assert pending[0]['contract_version']==2 and pending[0]['purpose']=='purchase_contract'
    execute, redirected, _ = setup(journal=reopened,origin='https://different.example.test/rest/v1/')
    with pytest.raises(EvidenceJournalUnavailable): asyncio.run(execute())
    assert not redirected
    execute, second, _ = setup(journal=reopened,result=receipt(duplicate=True))
    assert asyncio.run(execute())['duplicate']
    assert first[0].content == second[0].content
    assert reopened.load(uid(4))[1]=='confirmed'
    assert reopened.pending(workspace_id=uid(2),actor_id=uid(5))['items']==[]
    # Even confirmed history is checked with the database on deliberate retry.
    execute, third, _ = setup(journal=reopened,status=403)
    with pytest.raises(EvidencePersistenceUnconfirmed): asyncio.run(execute())
    assert third[0].content==first[0].content and reopened.load(uid(4))[1]=='unconfirmed'


def test_journal_mixed_targets_shared_capacity_and_exact_identity(tmp_path,monkeypatch):
    from tests.test_acquisition_evidence_attestation import sign as mail_sign
    tmp_path.chmod(0o700); journal=EvidenceJournal(tmp_path)
    monkeypatch.setattr('tools.acquisition_evidence_journal.MAX_JOURNAL_REQUESTS',2)
    journal.prepare(sign()); mail=mail_sign(); journal.prepare(mail)
    with pytest.raises(EvidenceJournalUnavailable): journal.prepare(sign() | {'p_id':str(uid(99))})
    assert journal.prepare(sign())==uid(4)
    with pytest.raises(EvidenceJournalUnavailable): journal.prepare(sign() | {'p_version':3})
    assert journal.load(uid(4))[0]==sign()


def test_cancelled_dispatch_stays_durable(tmp_path):
    tmp_path.chmod(0o700); journal=EvidenceJournal(tmp_path); journal.prepare(sign())
    async def scenario():
        entered=asyncio.Event()
        class Waiting(Stream):
            async def __aiter__(self):
                entered.set(); await asyncio.Event().wait(); yield b'never'
        stream=Waiting(); execute, calls, _ = setup(journal=journal,stream=stream)
        task=asyncio.create_task(execute()); await entered.wait(); task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
        assert stream.closed and len(calls)==1 and journal.load(uid(4))[1]=='unconfirmed'
    asyncio.run(scenario())


def test_journal_confirmation_failure_preserves_uncertainty(tmp_path,monkeypatch):
    tmp_path.chmod(0o700); journal=EvidenceJournal(tmp_path); journal.prepare(sign())
    def fail(*args): raise OSError('private disk failure')
    monkeypatch.setattr(journal,'confirm',fail)
    execute, calls, _ = setup(journal=journal)
    with pytest.raises(EvidencePersistenceUnconfirmed): asyncio.run(execute())
    assert len(calls)==1 and journal.load(uid(4))[1]=='unconfirmed'


@pytest.mark.parametrize('change', [{'contract_id':uid(99)}, {'contract_version':True}, {'purpose':'title_report'},
                                    {'session_id':uid(99)}, {'actor_id':uid(99)}])
def test_journal_scope_failure_preserves_prepared_request(tmp_path,change):
    tmp_path.chmod(0o700); journal=EvidenceJournal(tmp_path); journal.prepare(sign())
    execute, calls, _ = setup(journal=journal,scope=change)
    with pytest.raises(EvidenceJournalUnavailable): asyncio.run(execute())
    assert not calls and journal.load(uid(4))==(sign(),'prepared')


def test_mail_and_contract_dispatch_cannot_swap_journal_targets(tmp_path):
    from tests.test_acquisition_evidence_attestation import sign as mail_sign
    from tools.acquisition_evidence_journal import persist_journaled_observation
    tmp_path.chmod(0o700); journal=EvidenceJournal(tmp_path)
    journal.prepare(sign()); mail=mail_sign(); mail['p_id']=str(uid(99)); journal.prepare(mail)
    calls=[]
    async def attempt():
        async with httpx.AsyncClient(base_url='https://storage.example.test/rest/v1/',headers=AUTH,
                transport=httpx.MockTransport(lambda req:calls.append(req))) as client:
            with pytest.raises(EvidenceJournalUnavailable):
                await persist_journaled_observation(client,journal,uid(4),**SCOPE)
            with pytest.raises(EvidenceJournalUnavailable):
                await persist_journaled_contract_observation(client,journal,uid(99),**SCOPE)
    asyncio.run(attempt())
    assert not calls and journal.load(uid(4))[1]=='prepared' and journal.load(uid(99))[1]=='prepared'
