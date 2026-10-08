"""持续授权与上海自然日批次；与原投递占位共用同一个 SQLite 事务。"""
from __future__ import annotations
import json
import re
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
from tools.infra.persistence.delivery_attempt_store import DeliveryAttemptStore

SHANGHAI = ZoneInfo('Asia/Shanghai')

def utcnow():
    return datetime.now(timezone.utc)

def day_of(now):
    return now.astimezone(SHANGHAI).date().isoformat()

def ensure_schema(db):
    columns={r[1] for r in db.execute('PRAGMA table_info(attempts)')}
    if 'reserved_at' not in columns:
        db.execute('ALTER TABLE attempts ADD COLUMN reserved_at TEXT')
        db.execute('UPDATE attempts SET reserved_at=updated_at WHERE reserved_at IS NULL')
    db.execute('''CREATE TABLE IF NOT EXISTS daily_authorizations (
        id TEXT PRIMARY KEY, state TEXT NOT NULL, scope TEXT NOT NULL,
        maximum INTEGER NOT NULL, time TEXT NOT NULL, expires_at TEXT NOT NULL,
        ever_active INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS daily_runs (
        day TEXT PRIMARY KEY, id TEXT UNIQUE NOT NULL, authorization_id TEXT NOT NULL,
        state TEXT NOT NULL, reason TEXT NOT NULL, items TEXT NOT NULL,
        started_at TEXT NOT NULL, finished_at TEXT)''')

def authorization(db):
    row=db.execute('SELECT id,state,scope,maximum,time,expires_at,ever_active FROM daily_authorizations ORDER BY rowid DESC LIMIT 1').fetchone()
    if not row:return None
    return dict(id=row[0],state=row[1],scope=json.loads(row[2]),maximum=row[3],time=row[4],expires_at=row[5],ever_active=bool(row[6]))

def parse_time(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('daily_invalid_expiry')
    return result

def counts(db,now):
    day=day_of(now);confirmed=occupied=0
    for state,when in db.execute('SELECT state,reserved_at FROM attempts'):
        # 旧库时间为 UTC SQLite 时间；只读解释，不重写历史业务时间。
        at=datetime.fromisoformat(when.replace('Z','+00:00'))
        if at.tzinfo is None:at=at.replace(tzinfo=timezone.utc)
        if day_of(at)==day:
            confirmed+=state=='success';occupied+=state in {'success','unknown','in_flight'}
    unresolved=db.execute("SELECT COUNT(*) FROM attempts WHERE state IN ('unknown','in_flight')").fetchone()[0]
    return dict(day=day,confirmed=confirmed,occupied=occupied,remaining=max(0,3-occupied),unresolved=unresolved)

def shared_guard(db,now):
    if not db.execute('SELECT 1 FROM daily_authorizations WHERE ever_active=1').fetchone():return
    current=counts(db,now)
    if current['occupied']>=3:raise ValueError('daily_limit_reached')
    if current['unresolved']:raise ValueError('daily_unresolved')
    if db.execute("SELECT 1 FROM daily_runs WHERE state='running'").fetchone():raise ValueError('daily_busy')

class DailyDeliveryStore(DeliveryAttemptStore):
    def status(self):
        with self._connection() as db:
            auth=authorization(db);now=self.clock()
            if auth and auth['state'] in {'active','paused'} and parse_time(auth['expires_at'])<=now:
                auth={**auth,'state':'expired'}
            history=[]
            for row in db.execute('''SELECT r.day,r.id,r.state,r.reason,r.items,r.started_at,r.finished_at,b.authorized_max
                    FROM daily_runs r LEFT JOIN delivery_batches b ON b.batch_id=r.id ORDER BY r.day DESC LIMIT 14'''):
                attempts={r[0]:r[1] for r in db.execute('SELECT run_id,state FROM attempts WHERE batch_id=?',(row[1],))}
                items=json.loads(row[4])
                history.append(dict(day=row[0],id=row[1],state=row[2],reason=row[3],items=items,
                    started_at=row[5],finished_at=row[6],maximum=row[7] if row[7] is not None else len(items),
                    confirmed=sum(v=='success' for v in attempts.values()),
                    unresolved=sum(v in {'unknown','in_flight'} for v in attempts.values()),attempts=attempts))
            return dict(authorization=auth,today=counts(db,now),history=history)

    def save_draft(self,scope,maximum,time,expires_at):
        if type(maximum) is not int or not 1<=maximum<=3:raise ValueError('daily_invalid_limit')
        if not isinstance(time,str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',time):raise ValueError('daily_invalid_time')
        if not isinstance(expires_at,str) or parse_time(expires_at)<=self.clock():raise ValueError('daily_invalid_expiry')
        if not isinstance(scope,list) or len(scope)>30:raise ValueError('daily_invalid_scope')
        if len({i['run_id'] for i in scope})!=len(scope) or len({i['job_key'] for i in scope})!=len(scope):raise ValueError('daily_invalid_scope')
        if any(i['channel']!='liepin' or i['delivery_kind']!='generated_pdf' or not re.fullmatch('[a-f0-9]{64}',i['pdf_sha256']) for i in scope):raise ValueError('daily_invalid_scope')
        with self._connection() as db:
            old=authorization(db)
            if old and old['state'] not in {'draft','revoked'}:raise ValueError('daily_authorization_immutable')
            if db.execute("SELECT 1 FROM daily_runs WHERE state='running'").fetchone():raise ValueError('daily_busy')
            ref=old['id'] if old and old['state']=='draft' else uuid4().hex
            db.execute('INSERT OR REPLACE INTO daily_authorizations(id,state,scope,maximum,time,expires_at,created_at) VALUES(?,?,?,?,?,?,?)',
                       (ref,'draft',json.dumps(scope,ensure_ascii=False),maximum,time,expires_at,self.clock().isoformat()))
            return authorization(db)

    def set_status(self,ref,state,*,confirmed=False):
        if state not in {'active','paused','revoked'}:raise ValueError('daily_invalid_state')
        with self._connection() as db:
            a=authorization(db)
            if not a or a['id']!=ref or a['state']=='revoked':raise ValueError('daily_authorization_unavailable')
            if state=='active':
                if confirmed is not True:raise ValueError('daily_confirmation_required')
                if not a['scope']:raise ValueError('daily_empty_scope')
                if parse_time(a['expires_at'])<=self.clock():raise ValueError('daily_expired')
            elif state=='paused' and a['state']!='active':raise ValueError('daily_not_active')
            db.execute('UPDATE daily_authorizations SET state=?,ever_active=MAX(ever_active,?) WHERE id=?',(state,int(state=='active'),ref))
            return {**a,'state':state}

    def claim(self,*,force=False):
        with self._connection() as db:
            a=authorization(db);now=self.clock();day=day_of(now)
            def blocked(reason):return dict(claimed=False,reason=reason)
            if not a or a['state']!='active':return blocked('daily_not_active')
            if parse_time(a['expires_at'])<=now:return blocked('daily_expired')
            if db.execute('SELECT 1 FROM daily_runs WHERE day=?',(day,)).fetchone():return blocked('daily_already_run')
            if db.execute("SELECT 1 FROM daily_runs WHERE state='running'").fetchone() or counts(db,now)['unresolved']:return blocked('daily_unresolved')
            if not force and now.astimezone(SHANGHAI).strftime('%H:%M')<a['time']:return blocked('daily_not_due')
            used={r[0] for r in db.execute('SELECT job_key FROM attempts')}
            available=max(0,min(a['maximum'],3-counts(db,now)['occupied']))
            items=[i for i in a['scope'] if i['job_key'] not in used][:available]
            ref='daily_'+uuid4().hex
            db.execute('INSERT INTO daily_runs(day,id,authorization_id,state,reason,items,started_at) VALUES(?,?,?,?,?,?,?)',
                       (day,ref,a['id'],'running','',json.dumps(items,ensure_ascii=False),now.isoformat()))
            db.execute('INSERT INTO delivery_batches(batch_id,authorized_max,prior_attempt_ids,active,allowed_delivery_kind,authorization_ref) VALUES(?,?,?,0,?,?)',
                       (ref,a['maximum'],'[]','generated_pdf',ref))
            return dict(claimed=True,id=ref,items=items,maximum=a['maximum'])

    def _check(self,db,ref,run_id,digest):
        a=authorization(db);now=self.clock()
        if not a or a['state']!='active':raise ValueError('daily_not_active')
        if parse_time(a['expires_at'])<=now:raise ValueError('daily_expired')
        row=db.execute('SELECT day,authorization_id,state,items FROM daily_runs WHERE id=?',(ref,)).fetchone()
        if not row or row[1]!=a['id'] or row[2]!='running':raise ValueError('daily_run_unavailable')
        if row[0]!=day_of(now):raise ValueError('daily_date_changed')
        items=json.loads(row[3]);matches=[i for i in items if i['run_id']==run_id and i['pdf_sha256']==digest]
        if len(matches)!=1:raise ValueError('daily_scope_mismatch')
        if db.execute("SELECT 1 FROM attempts WHERE state IN ('unknown','in_flight') AND NOT (run_id=? AND batch_id=? AND state='in_flight')",(run_id,ref)).fetchone():raise ValueError('daily_unresolved')
        return matches[0]

    def check_write(self,ref,run_id,digest):
        with self._connection() as db:return self._check(db,ref,run_id,digest)

    def write_permit(self,ref,run_id,digest,*,attempt_id=None):
        with self._connection() as db:
            now=self.clock()
            deadline=datetime.combine(now.astimezone(SHANGHAI).date()+timedelta(days=1),datetime.min.time(),tzinfo=SHANGHAI)
            if ref:
                self._check(db,ref,run_id,digest)
                deadline=min(deadline,parse_time(authorization(db)['expires_at']))
            elif db.execute("SELECT 1 FROM daily_runs WHERE state='running'").fetchone():
                raise ValueError('daily_busy')
            if attempt_id:
                row=db.execute('SELECT reserved_at,state FROM attempts WHERE attempt_id=? AND run_id=? AND pdf_sha256=?',(attempt_id,run_id,digest)).fetchone()
                if not row or row[1]!='in_flight':raise ValueError('daily_attempt_unavailable')
                at=datetime.fromisoformat(row[0].replace('Z','+00:00'))
                if at.tzinfo is None:at=at.replace(tzinfo=timezone.utc)
                if day_of(at)!=day_of(now):raise ValueError('daily_date_changed')
            return dict(daily_cycle=ref,write_deadline_ms=int(deadline.timestamp()*1000))

    def reserve_daily(self,ref,run_id,job_key,digest):
        with self._connection() as db:
            item=self._check(db,ref,run_id,digest)
            if item['job_key']!=job_key:raise ValueError('daily_scope_mismatch')
            if db.execute('SELECT 1 FROM attempts WHERE job_key=?',(job_key,)).fetchone():return None
            a=authorization(db)
            if counts(db,self.clock())['occupied']>=3 or db.execute('SELECT COUNT(*) FROM attempts WHERE batch_id=?',(ref,)).fetchone()[0]>=a['maximum']:raise ValueError('daily_limit_reached')
            attempt=uuid4().hex
            db.execute('INSERT INTO attempts(job_key,attempt_id,run_id,pdf_sha256,state,batch_id,reserved_at) VALUES(?,?,?,?,?,?,?)',
                       (job_key,attempt,run_id,digest,'in_flight',ref,self.clock().isoformat()))
            return attempt

    def finish_cycle(self,ref,reason):
        with self._connection() as db:
            result=db.execute("UPDATE daily_runs SET state='finished',reason=?,finished_at=? WHERE id=? AND state='running'",(reason[:120],self.clock().isoformat(),ref))
            if result.rowcount!=1:raise ValueError('daily_run_unavailable')
