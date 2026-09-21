import json
import re
import threading
from pathlib import Path
from tempfile import TemporaryDirectory

from app.services.ai import AIProvider
from app.services.safety import review
from app.services.subtitles import make_srt
from app.services.video_assembler import VideoAssembler
from app.services.voice import VoiceProvider, VoiceSettings, VoiceStudioService
from app.services.youtube_service import YouTubeService


class CancelledError(RuntimeError):
    pass


def safe_slug(value, default='project'):
    clean = re.sub(r'[^a-zA-Z0-9]+', '-', (value or '').strip()).strip('-').lower()
    return clean or default


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

    def _completion_state(self, task_name, original_status, original_step):
        mapping = {
            'generate_script': ('needs_review', 'script'),
            'preview_voice': (original_status, 'voice'),
            'generate_voice': ('needs_review', 'voice'),
            'generate_subtitles': ('needs_review', 'subtitle'),
            'dub_video': ('needs_review', 'video'),
            'thumbnail_brief': ('needs_review', 'thumbnail'),
            'assemble_video': ('needs_review', 'video'),
            'safety_check': ('needs_review', 'safety'),
            'approve': ('approved', 'approval'),
            'upload_video': ('published', 'upload'),
        }
        return mapping.get(task_name, (original_status or 'draft', original_step or 'workflow'))

    def _run(self, run_id, project_id, task_name, settings):
        project_before = self.db.project(project_id)
        original_status = project_before['status'] if project_before else 'draft'
        original_step = project_before['workflow_step'] if project_before else 'project'
        try:
            with TemporaryDirectory(prefix='aiys-') as temp_dir:
                self.db.set_pipeline_temp_paths(run_id, [temp_dir])
                self._execute(run_id, project_id, task_name, settings, Path(temp_dir))
                final_status, final_step = self._completion_state(task_name, original_status, original_step)
                if task_name == 'upload_video':
                    project_row = self.db.project(project_id)
                    final_status = 'scheduled' if settings.get('publish_at') else 'published'
                    if project_row:
                        self.db.update_project(project_id, status=final_status, workflow_step='upload', progress=100)
                elif task_name == 'preview_voice':
                    self.db.update_project(project_id, status=final_status, workflow_step=final_step, progress=100)
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

    def _voice_settings(self, project):
        settings = VoiceSettings.from_project(project)
        if not settings.voice_profile:
            settings.voice_profile = project['voice_profile'] or ''
        if not settings.provider:
            settings.provider = project['voice_provider'] or 'sapi'
        if not settings.text_source_path:
            settings.text_source_path = project['text_source_path'] or ''
        if not settings.sample_path:
            settings.sample_path = project['voice_sample_path'] or ''
        return settings

    def _voice_provider(self, project, settings, voice_settings):
        return VoiceProvider(
            settings.get('voice_endpoint', ''),
            settings.get('voice_api_key', ''),
            voice_settings.voice_profile or settings.get('voice_id', ''),
            provider_type=voice_settings.provider,
            ffmpeg_path=settings.get('ffmpeg_path', 'ffmpeg'),
            http_timeout=settings.get('voice_http_timeout', 90),
        )

    def _output_dir(self, settings):
        return Path(settings.get('output_dir') or 'data/outputs')

    def _project_file(self, output_dir, project_id, project_name, suffix, label):
        stem = safe_slug(project_name or f'project-{project_id}', default=f'project-{project_id}')
        return output_dir / f'{stem}_{project_id}_{label}{suffix}'

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

        if task_name == 'preview_voice' or task_name == 'generate_voice':
            voice_settings = self._voice_settings(project)
            provider = self._voice_provider(project, settings, voice_settings)
            service = VoiceStudioService(provider, settings.get('ffmpeg_path', 'ffmpeg'))
            output_dir = self._output_dir(settings)
            output_dir.mkdir(parents=True, exist_ok=True)
            suffix = '.mp3' if voice_settings.output_format == 'mp3' else '.wav'
            label = 'preview_voice' if task_name == 'preview_voice' else 'voice'
            output_path = self._project_file(output_dir, project_id, project['name'], suffix, label)
            self._update(
                run_id,
                project_id,
                10,
                'Đang preview voice…' if task_name == 'preview_voice' else 'Đang tạo voice…',
                'voice',
            )
            self._check_cancel(project_id)
            source_path = project['srt_path'] or project['text_source_path'] or voice_settings.text_source_path or ''
            audio_path = service.generate_audio(
                project['script'],
                output_path,
                voice_settings,
                authorized=bool(project['voice_authorized']),
                source_path=source_path,
                preview=task_name == 'preview_voice',
                progress_callback=lambda percent, message: self._update(run_id, project_id, percent, message, 'voice'),
                cancel_callback=lambda: self._check_cancel(project_id),
            )
            self.db.update_project(
                project_id,
                voice_path=str(audio_path),
                voice_profile=voice_settings.voice_profile,
                voice_provider=voice_settings.provider,
                voice_settings_json=voice_settings.to_json(),
                voice_sample_path=voice_settings.sample_path,
                text_source_path=voice_settings.text_source_path,
            )
            self._update(run_id, project_id, 100, f'Đã tạo voice: {audio_path}', 'voice')
            return

        if task_name == 'generate_subtitles':
            self._update(run_id, project_id, 15, 'Đang tạo file SRT…', 'subtitle')
            self._check_cancel(project_id)
            if not (project['script'] or '').strip():
                raise RuntimeError('Project chưa có script để tạo subtitle.')
            output_dir = self._output_dir(settings)
            output_path = self._project_file(output_dir, project_id, project['name'], '.srt', 'subtitles')
            srt_path = make_srt(project['script'], output_path)
            self.db.update_project(project_id, srt_path=srt_path)
            self._update(run_id, project_id, 100, f'Đã tạo subtitle: {srt_path}', 'subtitle')
            return

        if task_name == 'dub_video':
            self._update(run_id, project_id, 10, 'Đang chuẩn bị lồng tiếng video…', 'voice')
            self._check_cancel(project_id)
            if not project['media_path']:
                raise RuntimeError('Project chưa có media_path/video nguồn để lồng tiếng.')
            voice_settings = self._voice_settings(project)
            provider = self._voice_provider(project, settings, voice_settings)
            service = VoiceStudioService(provider, settings.get('ffmpeg_path', 'ffmpeg'))
            output_dir = self._output_dir(settings)
            output_dir.mkdir(parents=True, exist_ok=True)
            audio_suffix = '.mp3' if voice_settings.output_format == 'mp3' else '.wav'
            audio_output = self._project_file(output_dir, project_id, project['name'], audio_suffix, 'dub_track')
            video_output = self._project_file(output_dir, project_id, project['name'], '.mp4', 'dubbed')
            source_path = project['srt_path'] or project['text_source_path'] or voice_settings.text_source_path or ''
            result = service.dub_video(
                project['media_path'],
                project['script'],
                audio_output,
                video_output,
                voice_settings,
                authorized=bool(project['voice_authorized']),
                source_path=source_path,
                progress_callback=lambda percent, message: self._update(run_id, project_id, percent, message, 'video'),
                cancel_callback=lambda: self._check_cancel(project_id),
            )
            if result['warnings']:
                self.db.append_pipeline_log(run_id, 'Cảnh báo dubbing: ' + ' | '.join(result['warnings']))
            self.db.update_project(
                project_id,
                voice_path=str(result['audio_path']),
                video_path=str(result['video_path']),
                voice_profile=voice_settings.voice_profile,
                voice_provider=voice_settings.provider,
                voice_settings_json=voice_settings.to_json(),
                voice_sample_path=voice_settings.sample_path,
                text_source_path=voice_settings.text_source_path,
            )
            self._update(run_id, project_id, 100, f'Đã tạo video lồng tiếng: {result["video_path"]}', 'video')
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
                voice_settings = self._voice_settings(project)
                provider = self._voice_provider(project, settings, voice_settings)
                service = VoiceStudioService(provider, settings.get('ffmpeg_path', 'ffmpeg'))
                output_voice = temp_dir / f'project_{project_id}_voice.{voice_settings.output_format}'
                source_path = project['srt_path'] or project['text_source_path'] or voice_settings.text_source_path or ''
                generated = service.generate_audio(
                    project['script'],
                    output_voice,
                    voice_settings,
                    authorized=bool(project['voice_authorized']),
                    source_path=source_path,
                    progress_callback=lambda percent, message: self._update(run_id, project_id, percent, message, 'voice'),
                    cancel_callback=lambda: self._check_cancel(project_id),
                )
                self.db.update_project(project_id, voice_path=str(generated))
                project = self.db.project(project_id)
            output_dir = self._output_dir(settings)
            output_file = self._project_file(output_dir, project_id, project['name'], '.mp4', 'assembled')
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
