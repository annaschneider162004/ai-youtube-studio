import json
import tempfile
import unittest
from pathlib import Path

from app.db import Database
from app.services.pipeline import PipelineManager


class DatabaseAndPipelineTests(unittest.TestCase):
    def test_migrates_legacy_projects_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / 'legacy.db'
            import sqlite3

            conn = sqlite3.connect(db_path)
            conn.execute(
                '''
                CREATE TABLE projects(
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
                    status TEXT DEFAULT 'draft',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                '''
            )
            conn.commit()
            conn.close()

            db = Database(db_path)
            columns = {row['name'] for row in db.conn.execute('PRAGMA table_info(projects)').fetchall()}
            self.assertIn('voice_profile', columns)
            self.assertIn('workflow_step', columns)
            self.assertIn('safety_report_json', columns)

    def test_pipeline_safety_then_approve(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / 'studio.db')
            account_id = db.add_account('user@example.com', 'channel-1', 'Test Channel', '{}')
            project_id = db.add_project(account_id, 'Project A', 'Topic A')
            db.update_project(
                project_id,
                title='A valid title',
                description='A long enough description for safety check.',
                tags_json=json.dumps(['tag1', 'tag2']),
                voice_authorized=1,
                media_authorized=1,
            )
            pipeline = PipelineManager(db)

            pipeline.start(project_id, 'safety_check', {})
            pipeline._threads[project_id].join(timeout=10)
            project = db.project(project_id)
            self.assertEqual('passed', project['safety_status'])
            self.assertEqual('needs_review', project['status'])

            pipeline.start(project_id, 'approve', {})
            pipeline._threads[project_id].join(timeout=10)
            project = db.project(project_id)
            self.assertEqual('approved', project['status'])
            latest = db.latest_pipeline(project_id)
            self.assertEqual('completed', latest['status'])


if __name__ == '__main__':
    unittest.main()
