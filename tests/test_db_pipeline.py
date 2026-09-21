import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.db import Database
from app.services.pipeline import PipelineManager


class DatabaseAndPipelineTests(unittest.TestCase):
    def _write_wav(self, path, duration_ms=500):
        import wave

        frame_rate = 16000
        frame_count = int(frame_rate * (duration_ms / 1000))
        with wave.open(str(path), 'wb') as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(frame_rate)
            handle.writeframes(b'\x00\x00' * frame_count)

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
            self.assertIn('voice_provider', columns)
            self.assertIn('voice_settings_json', columns)
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

    def test_generate_voice_pipeline_updates_project(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / 'studio.db')
            account_id = db.add_account('user@example.com', 'channel-1', 'Test Channel', '{}')
            project_id = db.add_project(account_id, 'Project Voice', 'Topic Voice')
            db.update_project(
                project_id,
                script='Xin chào từ Voice Studio',
                voice_authorized=1,
                voice_provider='sapi',
                voice_settings_json=json.dumps(
                    {
                        'provider': 'sapi',
                        'voice_profile': '',
                        'language': 'vi-VN',
                        'speed': 1.0,
                        'pitch': 0.0,
                        'emotion': '',
                        'pause_ms': 150,
                        'output_format': 'wav',
                        'clone_enabled': False,
                        'fit_strategy': 'speed',
                        'sample_path': '',
                        'text_source_path': '',
                    },
                    ensure_ascii=False,
                ),
            )
            pipeline = PipelineManager(db)

            def fake_generate_audio(_service, text, output_path, settings, **kwargs):
                self.assertEqual('Xin chào từ Voice Studio', text)
                self.assertEqual('wav', settings.output_format)
                self._write_wav(output_path, duration_ms=600)
                return Path(output_path)

            with patch('app.services.pipeline.VoiceStudioService.generate_audio', autospec=True, side_effect=fake_generate_audio):
                pipeline.start(project_id, 'generate_voice', {'output_dir': temp_dir})
                pipeline._threads[project_id].join(timeout=10)

            project = db.project(project_id)
            latest = db.latest_pipeline(project_id)
            self.assertEqual('completed', latest['status'])
            self.assertEqual('needs_review', project['status'])
            self.assertEqual('voice', project['workflow_step'])
            self.assertTrue(project['voice_path'].endswith('.wav'))
            self.assertTrue(Path(project['voice_path']).exists())

    def test_generate_voice_pipeline_uses_text_source_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / 'studio.db')
            account_id = db.add_account('user@example.com', 'channel-1', 'Test Channel', '{}')
            project_id = db.add_project(account_id, 'Project Text Source', 'Topic Text Source')
            text_source = Path(temp_dir) / 'voice.txt'
            text_source.write_text('Nội dung từ file txt', encoding='utf-8')
            db.update_project(
                project_id,
                script='Script cũ',
                text_source_path=str(text_source),
                voice_authorized=1,
                voice_provider='sapi',
                voice_settings_json=json.dumps(
                    {
                        'provider': 'sapi',
                        'voice_profile': '',
                        'language': 'vi-VN',
                        'speed': 1.0,
                        'pitch': 0.0,
                        'emotion': '',
                        'pause_ms': 150,
                        'output_format': 'wav',
                        'clone_enabled': False,
                        'fit_strategy': 'speed',
                        'sample_path': '',
                        'text_source_path': str(text_source),
                    },
                    ensure_ascii=False,
                ),
            )
            pipeline = PipelineManager(db)

            def fake_generate_audio(_service, text, output_path, settings, source_path='', **kwargs):
                self.assertEqual(str(text_source), source_path)
                self.assertEqual(str(text_source), settings.text_source_path)
                self._write_wav(output_path, duration_ms=500)
                return Path(output_path)

            with patch('app.services.pipeline.VoiceStudioService.generate_audio', autospec=True, side_effect=fake_generate_audio):
                pipeline.start(project_id, 'generate_voice', {'output_dir': temp_dir})
                pipeline._threads[project_id].join(timeout=10)

            project = db.project(project_id)
            self.assertEqual(str(text_source), project['text_source_path'])
            self.assertEqual('completed', db.latest_pipeline(project_id)['status'])

    def test_preview_voice_preserves_existing_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / 'studio.db')
            account_id = db.add_account('user@example.com', 'channel-1', 'Test Channel', '{}')
            project_id = db.add_project(account_id, 'Project Preview', 'Topic Preview')
            db.update_project(
                project_id,
                script='Preview text',
                status='needs_review',
                workflow_step='subtitle',
                voice_authorized=1,
                voice_provider='sapi',
                voice_settings_json=json.dumps(
                    {
                        'provider': 'sapi',
                        'voice_profile': '',
                        'language': 'vi-VN',
                        'speed': 1.0,
                        'pitch': 0.0,
                        'emotion': '',
                        'pause_ms': 150,
                        'output_format': 'wav',
                        'clone_enabled': False,
                        'fit_strategy': 'speed',
                        'sample_path': '',
                        'text_source_path': '',
                    },
                    ensure_ascii=False,
                ),
            )
            pipeline = PipelineManager(db)

            def fake_generate_audio(_service, text, output_path, settings, preview=False, **kwargs):
                self.assertTrue(preview)
                self._write_wav(output_path, duration_ms=300)
                return Path(output_path)

            with patch('app.services.pipeline.VoiceStudioService.generate_audio', autospec=True, side_effect=fake_generate_audio):
                pipeline.start(project_id, 'preview_voice', {'output_dir': temp_dir})
                pipeline._threads[project_id].join(timeout=10)

            project = db.project(project_id)
            latest = db.latest_pipeline(project_id)
            self.assertEqual('completed', latest['status'])
            self.assertEqual('needs_review', project['status'])
            self.assertEqual('voice', project['workflow_step'])
            self.assertTrue(project['voice_path'].endswith('.wav'))

    def test_generate_voice_pipeline_accepts_timed_audio_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / 'studio.db')
            account_id = db.add_account('user@example.com', 'channel-1', 'Test Channel', '{}')
            project_id = db.add_project(account_id, 'Project Timed', 'Topic Timed')
            subtitle_path = Path(temp_dir) / 'sample.srt'
            subtitle_path.write_text('1\n00:00:00,000 --> 00:00:02,000\nXin chào\n', encoding='utf-8')
            db.update_project(
                project_id,
                script='Xin chào',
                srt_path=str(subtitle_path),
                voice_authorized=1,
                voice_provider='sapi',
                voice_settings_json=json.dumps(
                    {
                        'provider': 'sapi',
                        'voice_profile': '',
                        'language': 'vi-VN',
                        'speed': 1.0,
                        'pitch': 0.0,
                        'emotion': '',
                        'pause_ms': 150,
                        'output_format': 'wav',
                        'clone_enabled': False,
                        'fit_strategy': 'speed',
                        'sample_path': '',
                        'text_source_path': '',
                    },
                    ensure_ascii=False,
                ),
            )
            pipeline = PipelineManager(db)

            def fake_generate_audio(_service, text, output_path, settings, source_path='', **kwargs):
                self.assertTrue(source_path.endswith('.srt'))
                self._write_wav(output_path, duration_ms=800)
                return {'audio_path': Path(output_path), 'warnings': ['segment warning']}

            with patch('app.services.pipeline.VoiceStudioService.generate_audio', autospec=True, side_effect=fake_generate_audio):
                pipeline.start(project_id, 'generate_voice', {'output_dir': temp_dir})
                pipeline._threads[project_id].join(timeout=10)

            project = db.project(project_id)
            latest = db.latest_pipeline(project_id)
            logs = db.pipeline_logs(project_id)
            self.assertEqual('completed', latest['status'])
            self.assertEqual('needs_review', project['status'])
            self.assertTrue(project['voice_path'].endswith('.wav'))
            self.assertTrue(any('Cảnh báo audio' in line for line in logs))

    def test_generate_voice_pipeline_requires_authorization(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / 'studio.db')
            account_id = db.add_account('user@example.com', 'channel-1', 'Test Channel', '{}')
            project_id = db.add_project(account_id, 'Project Unauthorized', 'Topic Unauthorized')
            db.update_project(
                project_id,
                script='Không được phép',
                voice_authorized=0,
                voice_provider='sapi',
                voice_settings_json=json.dumps(
                    {
                        'provider': 'sapi',
                        'voice_profile': '',
                        'language': 'vi-VN',
                        'speed': 1.0,
                        'pitch': 0.0,
                        'emotion': '',
                        'pause_ms': 150,
                        'output_format': 'wav',
                        'clone_enabled': False,
                        'fit_strategy': 'speed',
                        'sample_path': '',
                        'text_source_path': '',
                    },
                    ensure_ascii=False,
                ),
            )
            pipeline = PipelineManager(db)

            def fake_generate_audio(_service, text, output_path, settings, authorized=False, **kwargs):
                if not authorized:
                    raise PermissionError('Voice/TTS chỉ được chạy khi bạn xác nhận đang sở hữu hoặc có quyền sử dụng voice đó.')
                self._write_wav(output_path, duration_ms=500)
                return Path(output_path)

            with patch('app.services.pipeline.VoiceStudioService.generate_audio', autospec=True, side_effect=fake_generate_audio):
                pipeline.start(project_id, 'generate_voice', {'output_dir': temp_dir})
                pipeline._threads[project_id].join(timeout=10)

            project = db.project(project_id)
            latest = db.latest_pipeline(project_id)
            self.assertEqual('failed', latest['status'])
            self.assertEqual('failed', project['status'])
            self.assertIn('quyền sử dụng voice', latest['message'])

    def test_dub_video_pipeline_updates_audio_video_and_logs_warnings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            db = Database(Path(temp_dir) / 'studio.db')
            account_id = db.add_account('user@example.com', 'channel-1', 'Test Channel', '{}')
            project_id = db.add_project(account_id, 'Project Dub', 'Topic Dub')
            source_video = Path(temp_dir) / 'source.mp4'
            source_video.write_bytes(b'fake-video')
            subtitle_path = Path(temp_dir) / 'dub.srt'
            subtitle_path.write_text('1\n00:00:00,000 --> 00:00:01,500\nXin chào\n', encoding='utf-8')
            db.update_project(
                project_id,
                script='Xin chào',
                media_path=str(source_video),
                srt_path=str(subtitle_path),
                voice_authorized=1,
                voice_provider='sapi',
                voice_settings_json=json.dumps(
                    {
                        'provider': 'sapi',
                        'voice_profile': '',
                        'language': 'vi-VN',
                        'speed': 1.0,
                        'pitch': 0.0,
                        'emotion': '',
                        'pause_ms': 150,
                        'output_format': 'wav',
                        'clone_enabled': False,
                        'fit_strategy': 'speed',
                        'sample_path': '',
                        'text_source_path': '',
                    },
                    ensure_ascii=False,
                ),
            )
            pipeline = PipelineManager(db)

            def fake_dub_video(_service, video_path, text, output_audio_path, output_video_path, settings, **kwargs):
                self._write_wav(output_audio_path, duration_ms=700)
                Path(output_video_path).write_bytes(b'dubbed-video')
                return {
                    'audio_path': Path(output_audio_path),
                    'video_path': Path(output_video_path),
                    'warnings': ['audio longer than one segment'],
                }

            with patch('app.services.pipeline.VoiceStudioService.dub_video', autospec=True, side_effect=fake_dub_video):
                pipeline.start(project_id, 'dub_video', {'output_dir': temp_dir})
                pipeline._threads[project_id].join(timeout=10)

            project = db.project(project_id)
            latest = db.latest_pipeline(project_id)
            logs = db.pipeline_logs(project_id)
            self.assertEqual('completed', latest['status'])
            self.assertEqual('needs_review', project['status'])
            self.assertEqual('video', project['workflow_step'])
            self.assertTrue(project['voice_path'].endswith('.wav'))
            self.assertTrue(project['video_path'].endswith('.mp4'))
            self.assertTrue(any('Cảnh báo dubbing' in line for line in logs))


if __name__ == '__main__':
    unittest.main()
