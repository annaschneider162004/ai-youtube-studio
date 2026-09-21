import json, sqlite3
from pathlib import Path

class Database:
    def __init__(self, path='data/studio.db'):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.init()

    def init(self):
        self.conn.executescript('''
        CREATE TABLE IF NOT EXISTS accounts(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT, channel_id TEXT, channel_title TEXT, token_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS projects(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER, name TEXT, topic TEXT, script TEXT DEFAULT '',
            title TEXT DEFAULT '', description TEXT DEFAULT '', tags_json TEXT DEFAULT '[]',
            media_path TEXT DEFAULT '', voice_path TEXT DEFAULT '', thumbnail_path TEXT DEFAULT '',
            srt_path TEXT DEFAULT '', video_path TEXT DEFAULT '', status TEXT DEFAULT 'draft',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS uploads(
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER, account_id INTEGER,
            youtube_id TEXT, status TEXT, privacy TEXT, publish_at TEXT, error TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS analytics(
            id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER, channel_id TEXT,
            views INTEGER DEFAULT 0, subscribers INTEGER DEFAULT 0, video_count INTEGER DEFAULT 0,
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS scripts(id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER, topic TEXT, title TEXT, content TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS videos(id INTEGER PRIMARY KEY AUTOINCREMENT, account_id INTEGER, file_path TEXT, title TEXT, description TEXT, tags_json TEXT, privacy TEXT, publish_at TEXT, youtube_id TEXT, status TEXT DEFAULT 'draft', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        ''')
        self.conn.commit()

    def get_setting(self, key, default=''):
        row = self.conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return row['value'] if row else default

    def set_setting(self, key, value):
        self.conn.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))
        self.conn.commit()

    def accounts(self):
        return self.conn.execute('SELECT * FROM accounts ORDER BY id DESC').fetchall()

    def add_account(self, email, channel_id, channel_title, token_json):
        cur = self.conn.execute('INSERT INTO accounts(email,channel_id,channel_title,token_json) VALUES(?,?,?,?)', (email, channel_id, channel_title, token_json))
        self.conn.commit(); return cur.lastrowid

    def delete_account(self, account_id):
        self.conn.execute('DELETE FROM accounts WHERE id=?', (account_id,)); self.conn.commit()

    def projects(self):
        return self.conn.execute('SELECT p.*, a.channel_title FROM projects p LEFT JOIN accounts a ON a.id=p.account_id ORDER BY p.id DESC').fetchall()

    def add_project(self, account_id, name, topic):
        cur = self.conn.execute('INSERT INTO projects(account_id,name,topic) VALUES(?,?,?)', (account_id, name, topic))
        self.conn.commit(); return cur.lastrowid

    def update_project(self, project_id, **kw):
        allowed = {'account_id','name','topic','script','title','description','tags_json','media_path','voice_path','thumbnail_path','srt_path','video_path','status'}
        data = {k:v for k,v in kw.items() if k in allowed}
        if not data: return
        data['updated_at'] = __import__('datetime').datetime.now().isoformat(timespec='seconds')
        sql = 'UPDATE projects SET ' + ', '.join(f'{k}=?' for k in data) + ' WHERE id=?'
        self.conn.execute(sql, [*data.values(), project_id]); self.conn.commit()

    def delete_project(self, project_id):
        self.conn.execute('DELETE FROM projects WHERE id=?', (project_id,)); self.conn.commit()

    def add_upload(self, project_id, account_id, youtube_id='', status='pending', privacy='private', publish_at=None, error=''):
        cur = self.conn.execute('INSERT INTO uploads(project_id,account_id,youtube_id,status,privacy,publish_at,error) VALUES(?,?,?,?,?,?,?)', (project_id,account_id,youtube_id,status,privacy,publish_at,error))
        self.conn.commit(); return cur.lastrowid

    def uploads(self):
        return self.conn.execute('SELECT u.*,p.name project_name,a.channel_title FROM uploads u LEFT JOIN projects p ON p.id=u.project_id LEFT JOIN accounts a ON a.id=u.account_id ORDER BY u.id DESC').fetchall()

    def save_analytics(self, account_id, channel_id, views, subscribers, video_count):
        self.conn.execute('INSERT INTO analytics(account_id,channel_id,views,subscribers,video_count) VALUES(?,?,?,?,?)', (account_id,channel_id,views,subscribers,video_count)); self.conn.commit()

    def latest_analytics(self, account_id):
        return self.conn.execute('SELECT * FROM analytics WHERE account_id=? ORDER BY id DESC LIMIT 1', (account_id,)).fetchone()
