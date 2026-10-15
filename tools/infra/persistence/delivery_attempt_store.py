"""跨运行的投递占位；未知与中断记录不得自动重试。"""
from __future__ import annotations

import sqlite3
import json
import hashlib
import re
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4


def scoped_pdf_authorization_ref(run_id, job_key, pdf_sha256):
    body=json.dumps([run_id,job_key,pdf_sha256],ensure_ascii=False,separators=(',',':'))
    return 'pdfscope_'+hashlib.sha256(body.encode()).hexdigest()


class DeliveryAttemptStore:
    def __init__(self, path: Path = Path('outputs/submissions/delivery_attempts.sqlite3'), *, clock=None) -> None:
        self.path = path
        from datetime import datetime, timezone
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    @contextmanager
    def _connection(self):
        connection = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=10)
            connection.execute('BEGIN IMMEDIATE')
            connection.execute('''CREATE TABLE IF NOT EXISTS attempts (
                job_key TEXT PRIMARY KEY, attempt_id TEXT UNIQUE NOT NULL,
                run_id TEXT NOT NULL, pdf_sha256 TEXT NOT NULL,
                state TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            if 'batch_id' not in {row[1] for row in connection.execute('PRAGMA table_info(attempts)')}:
                connection.execute('ALTER TABLE attempts ADD COLUMN batch_id TEXT')
            connection.execute('''CREATE TABLE IF NOT EXISTS delivery_batches (
                batch_id TEXT PRIMARY KEY, authorized_max INTEGER NOT NULL,
                prior_attempt_ids TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)''')
            columns = {row[1] for row in connection.execute('PRAGMA table_info(delivery_batches)')}
            for name in ('allowed_delivery_kind', 'supplement_of', 'authorization_ref'):
                if name not in columns:
                    connection.execute(f'ALTER TABLE delivery_batches ADD COLUMN {name} TEXT')
            connection.execute('CREATE UNIQUE INDEX IF NOT EXISTS batch_authorization_ref ON delivery_batches(authorization_ref) WHERE authorization_ref IS NOT NULL')
            from tools.infra.persistence.daily_delivery import ensure_schema
            ensure_schema(connection)
            yield connection
            connection.commit()
        except (sqlite3.Error, OSError):
            if connection:
                connection.rollback()
            raise ValueError('delivery_state_unavailable') from None
        finally:
            if connection:
                connection.close()

    def has_attempt(self, job_key: str) -> bool:
        """准备审批时提前检查；真正发送仍必须原子占位。"""
        if not self.path.exists():
            return False
        with self._connection() as connection:
            return connection.execute('SELECT 1 FROM attempts WHERE job_key=?', (job_key,)).fetchone() is not None

    def reserve(self, job_key: str, run_id: str, pdf_sha256: str, *, delivery_kind: str | None = None) -> str | None:
        attempt_id = uuid4().hex
        with self._connection() as connection:
            if connection.execute('SELECT 1 FROM attempts WHERE job_key=?', (job_key,)).fetchone():
                return None
            from tools.infra.persistence.daily_delivery import shared_guard
            shared_guard(connection, self.clock())
            batch = self._active_batch(connection)
            if batch and batch['allowed_delivery_kind'] and batch['allowed_delivery_kind'] != delivery_kind:
                raise ValueError('delivery_batch_route_not_authorized')
            if batch and str(batch.get('authorization_ref') or '').startswith('pdfscope_') and batch['authorization_ref']!=scoped_pdf_authorization_ref(run_id,job_key,pdf_sha256):
                raise ValueError('delivery_scope_mismatch')
            if batch and batch['unresolved']:
                raise ValueError('delivery_batch_unresolved')
            if batch and batch['remaining'] <= 0:
                raise ValueError('delivery_batch_limit_reached')
            result = connection.execute(
                'INSERT OR IGNORE INTO attempts(job_key,attempt_id,run_id,pdf_sha256,state,batch_id,reserved_at) VALUES(?,?,?,?,?,?,?)',
                (job_key, attempt_id, run_id, pdf_sha256, 'in_flight', batch['batch_id'] if batch else None, self.clock().isoformat()),
            )
            return attempt_id if result.rowcount == 1 else None

    @staticmethod
    def _active_batch(connection) -> dict | None:
        batches = connection.execute('SELECT batch_id,authorized_max,allowed_delivery_kind,authorization_ref FROM delivery_batches WHERE active=1').fetchall()
        if not batches:
            return None
        if len(batches) != 1:
            raise ValueError('delivery_state_unavailable')
        batch_id, maximum, allowed_kind, authorization_ref = batches[0]
        states = dict(connection.execute('SELECT state,COUNT(*) FROM attempts WHERE batch_id=? GROUP BY state', (batch_id,)))
        consumed = sum(states.values())
        return {'batch_id':batch_id, 'authorized_max':maximum, 'consumed':consumed,
                'remaining':max(0,maximum-consumed), 'confirmed':states.get('success',0),
                'unresolved':states.get('unknown',0), 'in_flight':states.get('in_flight',0),
                'allowed_delivery_kind':allowed_kind,'authorization_ref':authorization_ref}

    def active_batch(self) -> dict | None:
        if not self.path.exists():
            return None
        with self._connection() as connection:
            return self._active_batch(connection)

    def authorize_batch(self, batch_id: str, authorized_max: int, prior_attempt_ids: list[str]) -> None:
        """记录明确的批次授权；已有授权不可通过重复调用重置或扩大。"""
        if (not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', batch_id) or type(authorized_max) is not int
                or authorized_max < 1 or len(set(prior_attempt_ids)) != len(prior_attempt_ids)
                or len(prior_attempt_ids) > authorized_max):
            raise ValueError('invalid_delivery_batch')
        prior = json.dumps(sorted(prior_attempt_ids))
        with self._connection() as connection:
            existing = connection.execute('SELECT authorized_max,prior_attempt_ids FROM delivery_batches WHERE batch_id=?', (batch_id,)).fetchone()
            if existing:
                if existing != (authorized_max, prior):
                    raise ValueError('delivery_batch_authorization_immutable')
                return
            if self._active_batch(connection):
                raise ValueError('delivery_batch_already_active')
            for attempt_id in prior_attempt_ids:
                row = connection.execute('SELECT batch_id FROM attempts WHERE attempt_id=?', (attempt_id,)).fetchone()
                if row is None or row[0] is not None:
                    raise ValueError('delivery_batch_prior_attempt_mismatch')
            connection.execute('INSERT INTO delivery_batches(batch_id,authorized_max,prior_attempt_ids) VALUES(?,?,?)', (batch_id,authorized_max,prior))
            connection.executemany('UPDATE attempts SET batch_id=? WHERE attempt_id=?', ((batch_id,a) for a in prior_attempt_ids))

    def authorize_supplementary_batch(self, batch_id: str, previous_batch_id: str, authorized_max: int,
                                      delivery_kind: str, authorization_ref: str) -> None:
        """仅在新的明确授权后创建补充批次；原额度和历史尝试保持独立。"""
        if (not all(isinstance(v, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,160}', v)
                    for v in (batch_id, previous_batch_id, authorization_ref))
                or type(authorized_max) is not int or authorized_max < 1
                or delivery_kind not in {'generated_pdf', 'platform_default'}):
            raise ValueError('invalid_delivery_batch')
        with self._connection() as connection:
            existing = connection.execute('SELECT authorized_max,supplement_of,allowed_delivery_kind,authorization_ref FROM delivery_batches WHERE batch_id=?', (batch_id,)).fetchone()
            if existing:
                if existing != (authorized_max, previous_batch_id, delivery_kind, authorization_ref):
                    raise ValueError('delivery_batch_authorization_immutable')
                return
            if connection.execute('SELECT 1 FROM delivery_batches WHERE authorization_ref=?', (authorization_ref,)).fetchone():
                raise ValueError('delivery_batch_authorization_already_used')
            previous = self._active_batch(connection)
            if (not previous or previous['batch_id'] != previous_batch_id or previous['remaining']
                    or previous['unresolved'] or previous['in_flight']):
                raise ValueError('delivery_batch_prior_unresolved')
            connection.execute('UPDATE delivery_batches SET active=0 WHERE batch_id=?', (previous_batch_id,))
            connection.execute('INSERT INTO delivery_batches(batch_id,authorized_max,prior_attempt_ids,allowed_delivery_kind,supplement_of,authorization_ref) VALUES(?,?,?,?,?,?)',
                               (batch_id, authorized_max, '[]', delivery_kind, previous_batch_id, authorization_ref))

    def finish(self, attempt_id: str, state: str) -> None:
        if state not in {'success', 'failed', 'unknown', 'not_submitted'}:
            raise ValueError('invalid_delivery_outcome')
        with self._connection() as connection:
            if state == 'not_submitted':
                result = connection.execute("DELETE FROM attempts WHERE attempt_id=? AND state='in_flight'", (attempt_id,))
            else:
                result = connection.execute(
                "UPDATE attempts SET state=?,updated_at=CURRENT_TIMESTAMP WHERE attempt_id=? AND state='in_flight'",
                (state, attempt_id),
                )
            if result.rowcount != 1:
                raise ValueError('delivery_attempt_already_finished')

    def confirm_unknown(self, attempt_id: str, run_id: str, resume_sha256: str) -> None:
        self.resolve_unknown(attempt_id, run_id, resume_sha256, 'success')

    def resolve_unknown(self, attempt_id: str, run_id: str, resume_sha256: str, state: str) -> None:
        """核验已有回执后终结占位；永不解除岗位防重。"""
        if state not in {'success', 'failed'}:
            raise ValueError('invalid_delivery_outcome')
        with self._connection() as connection:
            row = connection.execute('SELECT state FROM attempts WHERE attempt_id=? AND run_id=? AND pdf_sha256=?',
                                     (attempt_id,run_id,resume_sha256)).fetchone()
            if row is None or row[0] not in {'unknown', state}:
                raise ValueError('receipt_attempt_mismatch')
            connection.execute("UPDATE attempts SET state=?,updated_at=CURRENT_TIMESTAMP WHERE attempt_id=?",(state,attempt_id))
