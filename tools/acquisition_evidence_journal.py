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
from uuid import UUID

from tools.acquisition_evidence import EvidenceUnavailable, unique_json_object
from tools.acquisition_evidence_persistence import (
    SignedObservationRequest, EvidencePersistenceUnconfirmed, persist_evidence_attestation,
)


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
            db.execute('''CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, body TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('prepared','unconfirmed','confirmed')),
                receipt TEXT
            )''')
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
                db.execute('INSERT INTO requests VALUES (?, ?, ?, NULL)', (identity, body, 'prepared'))
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

    def mark_dispatch(self, identity, body):
        _, exact = self._body(body)
        with self._connect() as db:
            # A committed unconfirmed state precedes EVERY network attempt.
            changed = db.execute("UPDATE requests SET state='unconfirmed',receipt=NULL WHERE id=? AND body=?",
                                 (str(identity), exact)).rowcount
            if changed != 1:
                raise EvidenceJournalUnavailable('Original journal request unavailable')

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
    journal.mark_dispatch(identity, body)
    receipt = await persist_evidence_attestation(client, body, **scope)
    try:
        journal.confirm(identity, body, receipt)
    except (OSError, sqlite3.Error, EvidenceJournalUnavailable):
        raise EvidencePersistenceUnconfirmed('Evidence observation persistence is unconfirmed') from None
    return receipt
