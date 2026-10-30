"""Private single-host worker journal for exact signed-observation recovery.

The operator supplies a persistent private directory. No tokens or signing keys
are stored. This is not a distributed queue, approval ledger or live worker.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import stat
import httpx
from uuid import UUID

from tools.acquisition_evidence import EvidenceUnavailable, authenticated_origin, unique_json_object
from tools.acquisition_evidence_persistence import (
    SignedObservationRequest, EvidencePersistenceUnconfirmed, persist_evidence_attestation,
)


MAX_JOURNAL_REQUESTS = 10000


class EvidenceJournalUnavailable(EvidenceUnavailable):
    pass


class EvidenceJournal:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.path = self.directory / 'signed-observations.sqlite3'
        self._private_directory()
        # Exclusive creation prevents silently following a pre-existing symlink.
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        self._private_file()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, body TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('prepared','unconfirmed','confirmed')),
                receipt TEXT, destination TEXT
            )''')
            if 'destination' not in {row[1] for row in db.execute('PRAGMA table_info(requests)')}:
                db.execute('ALTER TABLE requests ADD COLUMN destination TEXT')
            db.execute("""CREATE INDEX IF NOT EXISTS pending_observation_scope
                ON requests(json_extract(body,'$.p_workspace'),json_extract(body,'$.p_actor'),id)
                WHERE state IN ('prepared','unconfirmed')""")
        # Make the initial directory entry durable before any provider dispatch.
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)

    def _private_directory(self):
        info = self.directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077):
            raise EvidenceJournalUnavailable('Private persistent journal directory required')

    def _private_file(self):
        self._private_directory()
        info = self.path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) & 0o077 or info.st_nlink != 1):
            raise EvidenceJournalUnavailable('Private journal file required')

    @contextmanager
    def _connect(self):
        self._private_file()
        db = sqlite3.connect(self.path, timeout=5)
        try:
            db.execute('PRAGMA journal_mode=DELETE')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA fullfsync=ON')
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _body(request):
        try:
            value = SignedObservationRequest.model_validate(request)
            # Preserve the signed text, regardless of envelope key order.
            body = json.dumps(value.model_dump(mode='json'), sort_keys=True, separators=(',', ':'), ensure_ascii=True)
            if len(body.encode()) > 12288:
                raise ValueError('Request exceeds journal limit')
            return str(value.p_id), body
        except (ValueError, TypeError, RecursionError):
            raise EvidenceJournalUnavailable('Valid bounded signed request required') from None

    def prepare(self, request):
        identity, body = self._body(request)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT body FROM requests WHERE id=?', (identity,)).fetchone()
            if old and old[0] != body:
                raise EvidenceJournalUnavailable('Exact original request required')
            if not old:
                # The admission check shares the write lock with insertion. Exact
                # recovery remains available even when new work is held. Nothing
                # is purged here, including confirmed history.
                if db.execute('SELECT count(*) FROM requests').fetchone()[0] >= MAX_JOURNAL_REQUESTS:
                    raise EvidenceJournalUnavailable('Journal capacity reached; retain existing requests for recovery')
                db.execute('INSERT INTO requests(id,body,state,receipt) VALUES (?, ?, ?, NULL)', (identity, body, 'prepared'))
        return UUID(identity)

    def load(self, identity: UUID):
        with self._connect() as db:
            row = db.execute('SELECT body,state FROM requests WHERE id=?', (str(identity),)).fetchone()
        if row is None:
            raise EvidenceJournalUnavailable('Saved signed request not found')
        body = json.loads(row[0], object_pairs_hook=unique_json_object)
        checked_id, _ = self._body(body)
        if checked_id != str(identity):
            raise EvidenceJournalUnavailable('Saved request identity mismatch')
        return body, row[1]

    def pending(self, *, workspace_id: UUID, actor_id: UUID, after: UUID | None = None, limit: int = 50):
        """Bounded discovery for a trusted worker, never an authorization service.

        Keep the original session reference for historical reconciliation. A new
        request can sort before a cursor; a later sweep must restart at None.
        No requests are dispatched, renewed or removed by this read.
        """
        if (not isinstance(workspace_id, UUID) or not isinstance(actor_id, UUID)
                or (after is not None and not isinstance(after, UUID))
                or type(limit) is not int or not 1 <= limit <= 100):
            raise EvidenceJournalUnavailable('Valid recovery scope and page size required')
        try:
            with self._connect() as db:
                rows = db.execute("""SELECT id,body,state FROM requests
                    WHERE json_extract(body,'$.p_workspace')=? AND json_extract(body,'$.p_actor')=?
                    AND state IN ('prepared','unconfirmed') AND id>?
                    ORDER BY id LIMIT ?""", (str(workspace_id), str(actor_id), str(after) if after else '', limit+1)).fetchall()
            items = []
            for identity, raw, state in rows:
                if len(raw.encode('utf-8')) > 12288:
                    raise ValueError('Oversized journal entry')
                body = json.loads(raw, object_pairs_hook=unique_json_object)
                checked_id, _ = self._body(body)
                if (checked_id != identity or body['p_workspace'] != str(workspace_id)
                        or body['p_actor'] != str(actor_id)):
                    raise ValueError('Recovery scope mismatch')
                items.append({'id': identity, 'campaign_id': body['p_campaign'],
                              'artifact_id': body['p_artifact'], 'session_id': body['p_session'], 'state': state})
            return {'items': items[:limit], 'next_after': items[limit-1]['id'] if len(items)>limit else None}
        except (ValueError, TypeError, KeyError, AttributeError, RecursionError, sqlite3.Error):
            raise EvidenceJournalUnavailable('Recovery journal could not be read') from None

    def mark_dispatch(self, identity, body, origin):
        _, exact = self._body(body)
        url = httpx.URL(origin)
        if (url.scheme != 'https' or not url.host or url.userinfo or url.query or url.fragment
                or url.path != '/rest/v1/'):
            raise EvidenceJournalUnavailable('Valid journal destination required')
        destination = str(url)
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT body,state,destination FROM requests WHERE id=?', (str(identity),)).fetchone()
            if not old or old[0] != exact:
                raise EvidenceJournalUnavailable('Original journal request unavailable')
            if old[2] is None and old[1] != 'prepared':
                # A pre-binding journal may already have sent this request. Never
                # guess its original destination from today's worker config.
                raise EvidenceJournalUnavailable('Original destination requires recovery review')
            if old[2] is not None and old[2] != destination:
                raise EvidenceJournalUnavailable('Original journal destination required')
            # Destination and uncertainty are durable before EVERY network attempt.
            db.execute("UPDATE requests SET state='unconfirmed',receipt=NULL,destination=? WHERE id=?",
                       (destination, str(identity)))

    def confirm(self, identity, body, receipt):
        _, exact = self._body(body)
        with self._connect() as db:
            changed = db.execute("UPDATE requests SET state='confirmed',receipt=? WHERE id=? AND body=? AND state='unconfirmed'",
                                 (json.dumps(receipt, sort_keys=True), str(identity), exact)).rowcount
            if changed != 1:
                raise EvidenceJournalUnavailable('Observation confirmation could not be saved')


async def persist_journaled_observation(client, journal: EvidenceJournal, identity: UUID, **scope):
    """Deliberately retry a journaled identity with current user-scoped credentials.

    Never return local receipt history as present authorization. Even a confirmed
    request is reconciled through the database again when deliberately retried.
    """
    body, _ = journal.load(identity)
    request = SignedObservationRequest.model_validate(body)
    expected = dict(workspace_id=request.p_workspace, campaign_id=request.p_campaign,
                    artifact_id=request.p_artifact, actor_id=request.p_actor, session_id=request.p_session)
    if scope != expected:
        raise EvidenceJournalUnavailable('Journal request scope mismatch')
    journal.mark_dispatch(identity, body, str(authenticated_origin(client)))
    receipt = await persist_evidence_attestation(client, body, **scope)
    try:
        journal.confirm(identity, body, receipt)
    except (OSError, sqlite3.Error, EvidenceJournalUnavailable):
        raise EvidencePersistenceUnconfirmed('Evidence observation persistence is unconfirmed') from None
    return receipt
