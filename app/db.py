import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


PROJECT_STATUSES = {
    'draft',
    'processing',
    'needs_review',
    'approved',
    'scheduled',
    'published',
    'failed',
}

PIPELINE_STATUSES = {
    'queued',
    'running',
    'cancelled',
    'completed',
    'failed',
}


class Database:
    def __init__(self, path='data/studio.db'):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connect()
        self.init()
        self.recover_incomplete_pipelines()

    def _connect(self):
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def init(self):
        self.conn.execute('PRAGMA foreign_keys = ON')
        self.conn.executescript(
            '''
            CREATE TABLE IF NOT EXISTS accounts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT,
                channel_id TEXT,
                channel_title TEXT,
                token_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS projects(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                name TEXT,
                topic TEXT,
                script TEXT DEFAULT '',
                title TEXT DEFAULT '',
                description TEXT DEFAULT '',
                tags_json TEXT DEFAULT '[]',
                media_path TEXT DEFAULT '',
                voice_path TEXT DEFAULT '',
                thumbnail_path TEXT DEFAULT '',
                srt_path TEXT DEFAULT '',
                video_path TEXT DEFAULT '',
                voice_profile TEXT DEFAULT '',
                thumbnail_brief TEXT DEFAULT '',
                status TEXT DEFAULT 'draft',
                workflow_step TEXT DEFAULT 'project',
                safety_status TEXT DEFAULT 'pending',
                safety_report_json TEXT DEFAULT '{}',
                voice_authorized INTEGER DEFAULT 0,
                media_authorized INTEGER DEFAULT 0,
                progress INTEGER DEFAULT 0,
                last_error TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS uploads(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                account_id INTEGER,
                youtube_id TEXT,
                status TEXT,
                privacy TEXT,
                publish_at TEXT,
                error TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS analytics(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                channel_id TEXT,
                views INTEGER DEFAULT 0,
                subscribers INTEGER DEFAULT 0,
                video_count INTEGER DEFAULT 0,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS settings(
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS scripts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                topic TEXT,
                title TEXT,
                content TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS videos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER,
                file_path TEXT,
                title TEXT,
                description TEXT,
                tags_json TEXT,
                privacy TEXT,
                publish_at TEXT,
                youtube_id TEXT,
                status TEXT DEFAULT 'draft',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS pipeline_runs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                task_name TEXT NOT NULL,
                status TEXT DEFAULT 'queued',
                progress INTEGER DEFAULT 0,
                message TEXT DEFAULT '',
                cancel_requested INTEGER DEFAULT 0,
                log_json TEXT DEFAULT '[]',
                temp_paths_json TEXT DEFAULT '[]',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
            '''
        )
        self._ensure_project_columns()
        self._ensure_pipeline_columns()
        self.conn.commit()

    def _existing_columns(self, table):
        rows = self.conn.execute(f'PRAGMA table_info({table})').fetchall()
        return {row['name'] for row in rows}

    def _ensure_project_columns(self):
        expected = {
            'voice_profile': "TEXT DEFAULT ''",
            'thumbnail_brief': "TEXT DEFAULT ''",
            'workflow_step': "TEXT DEFAULT 'project'",
            'safety_status': "TEXT DEFAULT 'pending'",
            'safety_report_json': "TEXT DEFAULT '{}'",
            'voice_authorized': 'INTEGER DEFAULT 0',
            'media_authorized': 'INTEGER DEFAULT 0',
            'progress': 'INTEGER DEFAULT 0',
            'last_error': "TEXT DEFAULT ''",
        }
        existing = self._existing_columns('projects')
        for column, definition in expected.items():
            if column not in existing:
                self.conn.execute(f'ALTER TABLE projects ADD COLUMN {column} {definition}')

    def _ensure_pipeline_columns(self):
        existing = self._existing_columns('pipeline_runs')
        expected = {
            'message': "TEXT DEFAULT ''",
            'cancel_requested': 'INTEGER DEFAULT 0',
            'log_json': "TEXT DEFAULT '[]'",
            'temp_paths_json': "TEXT DEFAULT '[]'",
            'updated_at': 'TEXT DEFAULT CURRENT_TIMESTAMP',
        }
        for column, definition in expected.items():
            if column not in existing:
                self.conn.execute(f'ALTER TABLE pipeline_runs ADD COLUMN {column} {definition}')

    @staticmethod
    def _now():
        return datetime.now().isoformat(timespec='seconds')

    def get_setting(self, key, default=''):
        row = self.conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row['value'] if row else default

    def set_setting(self, key, value):
        self.conn.execute(
            'INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
            (key, str(value)),
        )
        self.conn.commit()

    def backup_to(self, destination):
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(destination) as backup_conn:
            self.conn.backup(backup_conn)
        return destination

    def restore_from(self, source):
        source = Path(source)
        if not source.exists():
            raise FileNotFoundError(f'Không tìm thấy file backup: {source}')
        self.conn.close()
        shutil.copyfile(source, self.path)
        self._connect()
        self.init()
        self.recover_incomplete_pipelines()

    def accounts(self):
        return self.conn.execute('SELECT * FROM accounts ORDER BY id DESC').fetchall()

    def account(self, account_id):
        return self.conn.execute('SELECT * FROM accounts WHERE id=?', (account_id,)).fetchone()

    def add_account(self, email, channel_id, channel_title, token_json):
        cur = self.conn.execute(
            'INSERT INTO accounts(email,channel_id,channel_title,token_json) VALUES(?,?,?,?)',
            (email, channel_id, channel_title, token_json),
        )
        self.conn.commit()
        return cur.lastrowid

    def delete_account(self, account_id):
        self.conn.execute('DELETE FROM accounts WHERE id=?', (account_id,))
        self.conn.commit()

    def projects(self):
        return self.conn.execute(
            '''
            SELECT p.*, a.channel_title
            FROM projects p
            LEFT JOIN accounts a ON a.id=p.account_id
            ORDER BY p.id DESC
            '''
        ).fetchall()

    def project(self, project_id):
        return self.conn.execute(
            '''
            SELECT p.*, a.channel_title
            FROM projects p
            LEFT JOIN accounts a ON a.id=p.account_id
            WHERE p.id=?
            ''',
            (project_id,),
        ).fetchone()

    def add_project(self, account_id, name, topic):
        cur = self.conn.execute(
            'INSERT INTO projects(account_id,name,topic,status,workflow_step,safety_status) VALUES(?,?,?,?,?,?)',
            (account_id, name, topic, 'draft', 'project', 'pending'),
        )
        self.conn.commit()
        return cur.lastrowid

    def update_project(self, project_id, **kw):
        allowed = {
            'account_id',
            'name',
            'topic',
            'script',
            'title',
            'description',
            'tags_json',
            'media_path',
            'voice_path',
            'thumbnail_path',
            'srt_path',
            'video_path',
            'voice_profile',
            'thumbnail_brief',
            'status',
            'workflow_step',
            'safety_status',
            'safety_report_json',
            'voice_authorized',
            'media_authorized',
            'progress',
            'last_error',
        }
        data = {k: v for k, v in kw.items() if k in allowed}
        if 'status' in data and data['status'] not in PROJECT_STATUSES:
            raise ValueError(f'Trạng thái không hợp lệ: {data["status"]}')
        if not data:
            return
        data['updated_at'] = self._now()
        sql = 'UPDATE projects SET ' + ', '.join(f'{k}=?' for k in data) + ' WHERE id=?'
        self.conn.execute(sql, [*data.values(), project_id])
        self.conn.commit()

    def delete_project(self, project_id):
        self.conn.execute('DELETE FROM pipeline_runs WHERE project_id=?', (project_id,))
        self.conn.execute('DELETE FROM uploads WHERE project_id=?', (project_id,))
        self.conn.execute('DELETE FROM projects WHERE id=?', (project_id,))
        self.conn.commit()

    def recent_titles(self):
        rows = self.conn.execute(
            '''
            SELECT title FROM projects WHERE title IS NOT NULL AND trim(title) <> ''
            UNION ALL
            SELECT title FROM videos WHERE title IS NOT NULL AND trim(title) <> ''
            '''
        ).fetchall()
        return [row['title'] for row in rows]

    def add_upload(self, project_id, account_id, youtube_id='', status='pending', privacy='private', publish_at=None, error=''):
        cur = self.conn.execute(
            'INSERT INTO uploads(project_id,account_id,youtube_id,status,privacy,publish_at,error) VALUES(?,?,?,?,?,?,?)',
            (project_id, account_id, youtube_id, status, privacy, publish_at, error),
        )
        self.conn.commit()
        return cur.lastrowid

    def uploads(self):
        return self.conn.execute(
            '''
            SELECT u.*,p.name project_name,a.channel_title
            FROM uploads u
            LEFT JOIN projects p ON p.id=u.project_id
            LEFT JOIN accounts a ON a.id=u.account_id
            ORDER BY u.id DESC
            '''
        ).fetchall()

    def save_analytics(self, account_id, channel_id, views, subscribers, video_count):
        self.conn.execute(
            'INSERT INTO analytics(account_id,channel_id,views,subscribers,video_count) VALUES(?,?,?,?,?)',
            (account_id, channel_id, views, subscribers, video_count),
        )
        self.conn.commit()

    def latest_analytics(self, account_id):
        return self.conn.execute(
            'SELECT * FROM analytics WHERE account_id=? ORDER BY id DESC LIMIT 1',
            (account_id,),
        ).fetchone()

    def start_pipeline_run(self, project_id, task_name, message='Đã xếp hàng'):
        self.conn.execute(
            'UPDATE pipeline_runs SET status=?, updated_at=? WHERE project_id=? AND status IN (?, ?)',
            ('cancelled', self._now(), project_id, 'queued', 'running'),
        )
        cur = self.conn.execute(
            '''
            INSERT INTO pipeline_runs(project_id,task_name,status,progress,message,updated_at)
            VALUES(?,?,?,?,?,?)
            ''',
            (project_id, task_name, 'queued', 0, message, self._now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def append_pipeline_log(self, run_id, line):
        row = self.conn.execute('SELECT log_json FROM pipeline_runs WHERE id=?', (run_id,)).fetchone()
        logs = json.loads(row['log_json']) if row and row['log_json'] else []
        logs.append(f'[{self._now()}] {line}')
        self.conn.execute(
            'UPDATE pipeline_runs SET log_json=?, updated_at=? WHERE id=?',
            (json.dumps(logs, ensure_ascii=False), self._now(), run_id),
        )
        self.conn.commit()

    def set_pipeline_temp_paths(self, run_id, paths):
        self.conn.execute(
            'UPDATE pipeline_runs SET temp_paths_json=?, updated_at=? WHERE id=?',
            (json.dumps(list(paths), ensure_ascii=False), self._now(), run_id),
        )
        self.conn.commit()

    def update_pipeline_run(self, run_id, **kw):
        allowed = {'status', 'progress', 'message', 'cancel_requested'}
        data = {k: v for k, v in kw.items() if k in allowed}
        if 'status' in data and data['status'] not in PIPELINE_STATUSES:
            raise ValueError(f'Trạng thái pipeline không hợp lệ: {data["status"]}')
        if not data:
            return
        data['updated_at'] = self._now()
        sql = 'UPDATE pipeline_runs SET ' + ', '.join(f'{k}=?' for k in data) + ' WHERE id=?'
        self.conn.execute(sql, [*data.values(), run_id])
        self.conn.commit()

    def active_pipeline(self, project_id):
        return self.conn.execute(
            '''
            SELECT * FROM pipeline_runs
            WHERE project_id=? AND status IN ('queued','running')
            ORDER BY id DESC LIMIT 1
            ''',
            (project_id,),
        ).fetchone()

    def latest_pipeline(self, project_id):
        return self.conn.execute(
            'SELECT * FROM pipeline_runs WHERE project_id=? ORDER BY id DESC LIMIT 1',
            (project_id,),
        ).fetchone()

    def request_cancel_pipeline(self, project_id):
        self.conn.execute(
            '''
            UPDATE pipeline_runs
            SET cancel_requested=1, message=?, updated_at=?
            WHERE project_id=? AND status IN ('queued','running')
            ''',
            ('Đang chờ huỷ tác vụ…', self._now(), project_id),
        )
        self.conn.commit()

    def pipeline_logs(self, project_id):
        row = self.latest_pipeline(project_id)
        if not row or not row['log_json']:
            return []
        return json.loads(row['log_json'])

    def recover_incomplete_pipelines(self):
        running = self.conn.execute(
            "SELECT id, project_id FROM pipeline_runs WHERE status IN ('queued','running')"
        ).fetchall()
        for row in running:
            self.update_pipeline_run(
                row['id'],
                status='failed',
                progress=0,
                message='Ứng dụng đã đóng khi đang xử lý. Hãy thử chạy lại.',
            )
            self.update_project(
                row['project_id'],
                status='failed',
                last_error='Ứng dụng đã đóng khi đang xử lý. Hãy thử chạy lại.',
                progress=0,
            )
