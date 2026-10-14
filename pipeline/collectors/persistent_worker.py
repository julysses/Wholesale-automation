"""Restart-safe rehearsal tax collection/delivery worker. No PropStream orders.

One process owns a persistent state directory; interrupted collection requires
review, while interrupted delivery replays exactly the saved manifest set.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
PROJECT = 'tbhwxgfzbiaqjurghntj'


def connect(root):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(root / 'worker.sqlite')
    os.chmod(root / 'worker.sqlite', 0o600)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('''CREATE TABLE IF NOT EXISTS jobs (
      day TEXT NOT NULL, county TEXT NOT NULL, state TEXT NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0,
      reason TEXT, PRIMARY KEY(day,county))''')
    db.commit()
    return db


def collect(county, folder):
    from fetch_tax_roll import collect as fetch
    fetch(county, folder)


def deliver(folder):
    # Existing source-scoped Keychain credentials stay on this Mac.
    # Never copy browser sessions or fall back to an administrator credential.
    result = subprocess.run([sys.executable, str(ROOT / 'deliver_keychain.py'),
                             str(folder / 'manifests')], capture_output=True, timeout=3600)
    if result.returncode:
        raise RuntimeError('delivery_unconfirmed')


def tick(root, now=None, collector=collect, sender=deliver):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('Timezone-aware clock required')
    local = now.astimezone(ZoneInfo('America/Chicago'))
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / 'worker.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'status': 'busy'}
        db = connect(root)
        try:
            # A process crash could leave an incomplete downloaded archive. Never
            # regenerate a new collection/run ID on top of that uncertain state.
            db.execute("UPDATE jobs SET state='exception',reason='collection_interrupted' WHERE state='collecting'")
            if local.hour >= 6:
                for county in ('Dallas', 'Collin'):
                    db.execute("INSERT OR IGNORE INTO jobs(day,county,state) VALUES(?,?,'queued')",
                               (local.date().isoformat(), county))
            db.commit()
            rows = db.execute("SELECT * FROM jobs WHERE state IN ('queued','collected','delivering') AND retry_at<=? ORDER BY day,county", (now.timestamp(),)).fetchall()
            for job in rows:
                key = (job['day'], job['county'])
                folder = root / job['day'] / job['county'].lower()
                if job['state'] == 'queued':
                    # Do not collect an old scheduled day with today's source data.
                    if job['day'] != local.date().isoformat():
                        db.execute("UPDATE jobs SET state='exception',reason='collection_window_missed' WHERE day=? AND county=?", key)
                        db.commit()
                        continue
                    db.execute("UPDATE jobs SET state='collecting' WHERE day=? AND county=?", key)
                    db.commit()
                    try:
                        collector(job['county'], folder)
                    except Exception:
                        db.execute("UPDATE jobs SET state='exception',reason='collection_failed' WHERE day=? AND county=?", key)
                        db.commit()
                        continue
                    db.execute("UPDATE jobs SET state='collected' WHERE day=? AND county=?", key)
                    db.commit()
                attempts = job['attempts'] + 1
                # Commit before the network side effect. After a crash, sender
                # reconciles the same run IDs and journal instead of recollecting.
                if attempts > 3:
                    db.execute("UPDATE jobs SET state='exception',reason='delivery_retry_limit' WHERE day=? AND county=?", key)
                    db.commit()
                    continue
                db.execute("UPDATE jobs SET state='delivering',attempts=? WHERE day=? AND county=?", (attempts, *key))
                db.commit()
                try:
                    sender(folder)
                except Exception:
                    db.execute("UPDATE jobs SET state=?,reason='delivery_unconfirmed',retry_at=? WHERE day=? AND county=?",
                               ('exception' if attempts == 3 else 'delivering', now.timestamp() + 300 * attempts, *key))
                else:
                    db.execute("UPDATE jobs SET state='accepted',reason=NULL WHERE day=? AND county=?", key)
                db.commit()
            jobs = [dict(row) for row in db.execute('SELECT * FROM jobs ORDER BY day,county')]
            status = {'project': PROJECT, 'checked_at': now.isoformat(), 'jobs': jobs,
                      'exceptions': [row for row in jobs if row['state'] == 'exception'],
                      'foreclosure_collection': 'browser_worker_required',
                      'propstream': 'approved_connection_required',
                      'trace_spend_cents': 0, 'outreach_sent': False}
            tmp = root / 'status.json.tmp'
            tmp.write_text(json.dumps(status, indent=2)); tmp.chmod(0o600)
            tmp.replace(root / 'status.json')
            return status
        finally:
            db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    while True:
        status = tick(args.state)
        # No source records, credentials or raw exception contents in logs.
        print(json.dumps({'status': status.get('status', 'checked'),
                          'exception_count': len(status.get('exceptions', []))}), flush=True)
        if args.once:
            return
        time.sleep(60)


if __name__ == '__main__':
    main()
