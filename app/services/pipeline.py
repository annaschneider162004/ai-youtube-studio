import json
import threading
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.ai import AIProvider
from app.services.safety import review
from app.services.subtitles import make_srt
from app.services.video_assembler import VideoAssembler
from app.services.voice import VoiceProvider
from app.services.youtube_service import YouTubeService


class CancelledError(RuntimeError):
    pass


class PipelineManager:
    def __init__(self, db):
        self.db = db
        self._threads = {}

    def start(self, project_id, task_name, settings):
        existing = self.db.active_pipeline(project_id)
        if existing:
            raise RuntimeError('Project đang có tác vụ nền khác chạy.')
        run_id = self.db.start_pipeline_run(project_id, task_name)
        thread = threading.Thread(
            target=self._run,
            args=(run_id, project_id, task_name, dict(settings or {})),
            daemon=True,
        )
        self._threads[project_id] = thread
        thread.start()
        return run_id

    def cancel(self, project_id):
        self.db.request_cancel_pipeline(project_id)

    def _check_cancel(self, project_id):
        row = self.db.active_pipeline(project_id)
        if row and row['cancel_requested']:
            raise CancelledError('Người dùng đã yêu cầu huỷ tác vụ.')

    def _update(self, run_id, project_id, progress, message, workflow_step=None):
        self.db.update_pipeline_run(run_id, status='running', progress=progress, message=message)
        self.db.append_pipeline_log(run_id, message)
        update_kwargs = {'status': 'processing', 'progress': progress, 'last_error': ''}
        if workflow_step:
            update_kwargs['workflow_step'] = workflow_step
        self.db.update_project(project_id, **update_kwargs)

    def _run(self, run_id, project_id, task_name, settings):
        try:
            with TemporaryDirectory(prefix='aiys-') as temp_dir:
                self.db.set_pipeline_temp_paths(run_id, [temp_dir])
                self._execute(run_id, project_id, task_name, settings, Path(temp_dir))
                final_status = 'approved' if task_name == 'approve' else 'needs_review'
                final_step = {
                    'generate_script': 'script',
                    'generate_subtitles': 'subtitle',
                    'thumbnail_brief': 'thumbnail',
                    'assemble_video': 'video',
                    'safety_check': 'safety',
                    'approve': 'approval',
                    'upload_video': 'upload',
                }.get(task_name, 'workflow')
                if task_name == 'upload_video':
                    project_row = self.db.project(project_id)
                    final_status = 'scheduled' if settings.get('publish_at') else 'published'
                    if project_row and project_row['status'] == 'approved':
                        self.db.update_project(project_id, status=final_status, workflow_step='upload', progress=100)
                    else:
                        self.db.update_project(project_id, status=final_status, workflow_step='upload', progress=100)
                self.db.update_pipeline_run(run_id, status='completed', progress=100, message='Hoàn tất.')
                self.db.update_project(project_id, status=final_status, progress=100, workflow_step=final_step)
        except CancelledError as exc:
            self.db.update_pipeline_run(run_id, status='cancelled', progress=0, message=str(exc))
            self.db.append_pipeline_log(run_id, str(exc))
            self.db.update_project(project_id, status='draft', progress=0, last_error=str(exc))
        except Exception as exc:
            self.db.update_pipeline_run(run_id, status='failed', progress=0, message=str(exc))
            self.db.append_pipeline_log(run_id, f'Lỗi: {exc}')
            self.db.update_project(project_id, status='failed', progress=0, last_error=str(exc))
        finally:
            self._threads.pop(project_id, None)

    def _execute(self, run_id, project_id, task_name, settings, temp_dir):
        project = self.db.project(project_id)
        if not project:
            raise RuntimeError('Không tìm thấy project.')
        if task_name == 'generate_script':
            self._update(run_id, project_id, 10, 'Đang tạo script…', 'script')
            self._check_cancel(project_id)
            provider = AIProvider(
                settings.get('ai_endpoint', ''),
                settings.get('ai_api_key', ''),
                settings.get('ai_model', ''),
            )
            language = 'Vietnamese' if settings.get('locale', 'vi-VN').startswith('vi') else 'English'
            script = provider.generate_script(project['topic'] or project['name'], language)
            self.db.update_project(project_id, script=script)
            self._update(run_id, project_id, 100, 'Đã tạo script.', 'script')
            return

        if task_name == 'generate_subtitles':
            self._update(run_id, project_id, 15, 'Đang tạo file SRT…', 'subtitle')
            self._check_cancel(project_id)
            if not (project['script'] or '').strip():
                raise RuntimeError('Project chưa có script để tạo subtitle.')
            output_dir = Path(settings.get('output_dir') or 'data/outputs')
            output_path = output_dir / f'project_{project_id}.srt'
            srt_path = make_srt(project['script'], output_path)
            self.db.update_project(project_id, srt_path=srt_path)
            self._update(run_id, project_id, 100, f'Đã tạo subtitle: {srt_path}', 'subtitle')
            return

        if task_name == 'thumbnail_brief':
            self._update(run_id, project_id, 15, 'Đang tạo brief thumbnail…', 'thumbnail')
            self._check_cancel(project_id)
            title = project['title'] or project['topic'] or project['name']
            brief = (
                f'Thumbnail brief cho {title}\n\n'
                '• 1 chủ thể rõ ràng\n'
                '• Chữ lớn, dễ đọc\n'
                '• Tương phản mạnh\n'
                '• Trung thực với nội dung video\n'
                '• Tránh claim gây hiểu nhầm\n'
            )
            self.db.update_project(project_id, thumbnail_brief=brief)
            self._update(run_id, project_id, 100, 'Đã tạo brief thumbnail.', 'thumbnail')
            return

        if task_name == 'assemble_video':
            self._update(run_id, project_id, 10, 'Chuẩn bị ghép video…', 'video')
            self._check_cancel(project_id)
            if not project['media_path']:
                raise RuntimeError('Project chưa có media_path để ghép video.')
            if not project['voice_path']:
                provider = VoiceProvider(
                    settings.get('voice_endpoint', ''),
                    settings.get('voice_api_key', ''),
                    project['voice_profile'] or settings.get('voice_id', ''),
                )
                output_voice = temp_dir / f'project_{project_id}_voice.wav'
                provider.generate(
                    project['script'],
                    output_voice,
                    authorized=bool(project['voice_authorized']),
                    subtitles=project['srt_path'] or None,
                )
                self.db.update_project(project_id, voice_path=str(output_voice))
                project = self.db.project(project_id)
            output_dir = Path(settings.get('output_dir') or 'data/outputs')
            output_file = output_dir / f'project_{project_id}.mp4'
            assembler = VideoAssembler(settings.get('ffmpeg_path', 'ffmpeg'))
            assembler.assemble(
                project['media_path'],
                project['voice_path'],
                output_file,
                project['srt_path'] or None,
                progress_callback=lambda percent, message: self._update(run_id, project_id, percent, message, 'video'),
            )
            self.db.update_project(project_id, video_path=str(output_file))
            self._update(run_id, project_id, 100, f'Đã ghép video: {output_file}', 'video')
            return

        if task_name == 'safety_check':
            self._update(run_id, project_id, 20, 'Đang chạy safety check…', 'safety')
            self._check_cancel(project_id)
            result = review(
                project['title'],
                project['description'],
                recent_titles=[title for title in self.db.recent_titles() if title != project['title']],
                voice_authorized=bool(project['voice_authorized']),
                media_authorized=bool(project['media_authorized']),
                thumbnail_path=project['thumbnail_path'],
                video_path=project['video_path'],
            )
            safety_status = 'blocked' if result['blocked'] else 'passed'
            self.db.update_project(
                project_id,
                safety_status=safety_status,
                safety_report_json=json.dumps(result, ensure_ascii=False),
                workflow_step='safety',
            )
            self._update(
                run_id,
                project_id,
                100,
                'Safety check chặn publish.' if result['blocked'] else 'Safety check hoàn tất.',
                'safety',
            )
            return

        if task_name == 'approve':
            self._update(run_id, project_id, 60, 'Đang đánh dấu human approval…', 'approval')
            self._check_cancel(project_id)
            if project['safety_status'] != 'passed':
                raise RuntimeError('Phải chạy safety check thành công trước khi approve.')
            self.db.update_project(project_id, status='approved', workflow_step='approval')
            self._update(run_id, project_id, 100, 'Đã duyệt thủ công cho project.', 'approval')
            return

        if task_name == 'upload_video':
            self._update(run_id, project_id, 10, 'Đang chuẩn bị upload YouTube…', 'upload')
            self._check_cancel(project_id)
            if project['status'] != 'approved':
                raise RuntimeError('Project phải được human-approve trước khi upload/schedule.')
            account = self.db.account(project['account_id'])
            if not account:
                raise RuntimeError('Không tìm thấy account/channel cho project.')
            privacy = settings.get('privacy', 'private')
            publish_at = settings.get('publish_at') or None
            service = YouTubeService(account['token_json'])
            response = service.upload(
                project['video_path'],
                project['title'],
                project['description'],
                [item.strip() for item in json.loads(project['tags_json'] or '[]')],
                privacy=privacy,
                publish_at=publish_at,
                progress_callback=lambda percent, message: self._update(run_id, project_id, percent, message, 'upload'),
            )
            status = 'scheduled' if publish_at else 'published'
            self.db.add_upload(project_id, account['id'], response.get('id', ''), status, privacy, publish_at)
            self.db.update_project(project_id, status=status, workflow_step='upload')
            self._update(run_id, project_id, 100, f'Upload thành công. Video ID: {response.get("id", "")}', 'upload')
            return

        raise RuntimeError(f'Tác vụ pipeline chưa được hỗ trợ: {task_name}')
