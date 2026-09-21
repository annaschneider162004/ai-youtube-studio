from __future__ import annotations

import base64
import contextlib
import json
import platform
import re
import shutil
import subprocess
import tempfile
import wave
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import requests

from app.services.subtitles import SubtitleCue, parse_subtitle_file, split_script_lines
from app.services.video_assembler import VideoAssembler

SUPPORTED_AUDIO_SAMPLE_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.ogg', '.flac'}
SUPPORTED_AUDIO_OUTPUTS = {'wav', 'mp3'}
SUPPORTED_PROVIDERS = {'sapi', 'http'}
DEFAULT_SAMPLE_RATE = 16_000
DEFAULT_CHANNELS = 1
DEFAULT_SAMPLE_WIDTH = 2
MAX_SAMPLE_BYTES = 15 * 1024 * 1024
MAX_SAMPLE_DURATION_MS = 180_000


@dataclass(frozen=True)
class VoiceCapabilities:
    supports_cloning: bool = False
    supports_speed: bool = True
    supports_pitch: bool = False
    supports_emotion: bool = False
    supports_pause: bool = False
    supports_segmented_srt: bool = True


@dataclass(frozen=True)
class VoiceSampleInfo:
    path: str
    extension: str
    size_bytes: int
    duration_ms: int


@dataclass
class VoiceSettings:
    provider: str = 'sapi'
    voice_profile: str = ''
    language: str = 'vi-VN'
    speed: float = 1.0
    pitch: float = 0.0
    emotion: str = ''
    pause_ms: int = 150
    output_format: str = 'wav'
    clone_enabled: bool = False
    fit_strategy: str = 'speed'
    sample_path: str = ''
    text_source_path: str = ''

    @classmethod
    def from_project(cls, project):
        raw = project['voice_settings_json'] if project and 'voice_settings_json' in project.keys() else '{}'
        data = json.loads(raw or '{}')
        data.setdefault('provider', project['voice_provider'] if project and 'voice_provider' in project.keys() else 'sapi')
        data.setdefault('voice_profile', project['voice_profile'] if project and 'voice_profile' in project.keys() else '')
        data.setdefault('sample_path', project['voice_sample_path'] if project and 'voice_sample_path' in project.keys() else '')
        data.setdefault('text_source_path', project['text_source_path'] if project and 'text_source_path' in project.keys() else '')
        return cls(**{key: data.get(key, getattr(cls(), key)) for key in cls.__dataclass_fields__})

    def to_json(self):
        return json.dumps(asdict(self), ensure_ascii=False)

    def validate(self, ffmpeg_path='ffmpeg'):
        provider = (self.provider or 'sapi').strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f'Provider không được hỗ trợ: {self.provider}')
        if self.output_format.lower() not in SUPPORTED_AUDIO_OUTPUTS:
            raise ValueError('Chỉ hỗ trợ xuất WAV hoặc MP3.')
        if not 0.5 <= float(self.speed) <= 2.0:
            raise ValueError('Tốc độ voice phải nằm trong khoảng 0.5 đến 2.0.')
        if not -12.0 <= float(self.pitch) <= 12.0:
            raise ValueError('Pitch phải nằm trong khoảng -12 đến 12.')
        if not 0 <= int(self.pause_ms) <= 5_000:
            raise ValueError('Khoảng nghỉ phải nằm trong khoảng 0 đến 5000 ms.')
        if self.fit_strategy not in {'warn', 'speed', 'trim'}:
            raise ValueError('Fit strategy chỉ hỗ trợ warn, speed hoặc trim.')
        if self.sample_path:
            validate_voice_sample(self.sample_path, ffmpeg_path=ffmpeg_path)
        if self.clone_enabled and not self.sample_path:
            raise ValueError('Voice cloning yêu cầu upload mẫu giọng hợp lệ.')
        return True


@dataclass(frozen=True)
class TimedSegment:
    index: int
    start_ms: int
    end_ms: int
    text: str

    @property
    def duration_ms(self):
        return max(self.end_ms - self.start_ms, 0)


class BaseVoiceAdapter:
    capabilities = VoiceCapabilities()

    def __init__(self, endpoint='', api_key='', voice_id='', ffmpeg_path='ffmpeg', http_timeout=90):
        self.endpoint = endpoint or ''
        self.api_key = api_key or ''
        self.voice_id = voice_id or ''
        self.ffmpeg_path = ffmpeg_path or 'ffmpeg'
        self.http_timeout = int(http_timeout or 90)

    def configured(self):
        raise NotImplementedError

    def generate(self, text, output_path, settings, authorized=False, progress_callback=None):
        raise NotImplementedError


class SapiVoiceAdapter(BaseVoiceAdapter):
    capabilities = VoiceCapabilities(supports_speed=True, supports_segmented_srt=True)

    @staticmethod
    def _powershell():
        return shutil.which('powershell') or shutil.which('pwsh')

    def configured(self):
        return platform.system() == 'Windows' and bool(self._powershell())

    def generate(self, text, output_path, settings, authorized=False, progress_callback=None):
        ensure_voice_authorized(authorized, clone_enabled=settings.clone_enabled or bool(settings.sample_path))
        if settings.clone_enabled or settings.sample_path:
            raise NotImplementedError('Provider local SAPI không hỗ trợ voice cloning. Hãy dùng HTTP provider có hỗ trợ clone.')
        if not self.configured():
            raise NotImplementedError(
                'Provider local SAPI chỉ sẵn sàng trên Windows có PowerShell/System.Speech. '
                'Nếu bạn đang chạy môi trường khác, hãy chọn HTTP provider hoặc chạy bản .exe Windows.'
            )
        text = (text or '').strip()
        if not text:
            raise ValueError('Không có nội dung văn bản để tạo voice.')
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        target_wav = output_path if output_path.suffix.lower() == '.wav' else output_path.with_suffix('.wav')
        with tempfile.TemporaryDirectory(prefix='aiys-voice-') as temp_dir:
            temp_dir = Path(temp_dir)
            text_path = temp_dir / 'input.txt'
            script_path = temp_dir / 'sapi_tts.ps1'
            text_path.write_text(text, encoding='utf-8')
            script_path.write_text(
                """
param(
    [string]$TextPath,
    [string]$OutputPath,
    [string]$VoiceName,
    [int]$Rate
)
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    if ($VoiceName) { $synth.SelectVoice($VoiceName) }
    $synth.Rate = $Rate
    $synth.SetOutputToWaveFile($OutputPath)
    $content = Get-Content -LiteralPath $TextPath -Raw -Encoding UTF8
    $synth.Speak($content)
}
finally {
    $synth.Dispose()
}
""".strip(),
                encoding='utf-8',
            )
            if progress_callback:
                progress_callback(15, 'Đang gọi Windows SAPI để tạo giọng nói…')
            rate = max(-10, min(10, int(round((float(settings.speed) - 1.0) * 10))))
            command = [
                self._powershell(),
                '-NoProfile',
                '-ExecutionPolicy',
                'Bypass',
                '-File',
                str(script_path),
                str(text_path),
                str(target_wav),
                settings.voice_profile or self.voice_id,
                str(rate),
            ]
            completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if completed.returncode != 0:
                message = (completed.stderr or completed.stdout or '').strip()
                raise RuntimeError(f'Windows SAPI thất bại: {message or "không rõ nguyên nhân"}')
        if progress_callback:
            progress_callback(80, 'Đã tạo WAV local, đang kiểm tra output…')
        validate_audio_output(target_wav, expect_extension='.wav', ffmpeg_path=self.ffmpeg_path)
        if output_path.suffix.lower() == '.mp3':
            convert_audio_format(target_wav, output_path, self.ffmpeg_path)
            validate_audio_output(output_path, expect_extension='.mp3', ffmpeg_path=self.ffmpeg_path)
            target_wav.unlink(missing_ok=True)
            final_path = output_path
        else:
            final_path = target_wav
        if progress_callback:
            progress_callback(100, f'Đã tạo audio: {final_path}')
        return Path(final_path)


class HttpVoiceAdapter(BaseVoiceAdapter):
    capabilities = VoiceCapabilities(
        supports_cloning=True,
        supports_speed=True,
        supports_pitch=True,
        supports_emotion=True,
        supports_pause=True,
        supports_segmented_srt=True,
    )

    def configured(self):
        return bool(self.endpoint)

    def generate(self, text, output_path, settings, authorized=False, progress_callback=None):
        ensure_voice_authorized(authorized, clone_enabled=settings.clone_enabled or bool(settings.sample_path))
        if not self.configured():
            raise NotImplementedError(
                'HTTP voice provider chưa được cấu hình. Hãy nhập Voice endpoint trong Settings hoặc biến môi trường AIYS_VOICE_ENDPOINT.'
            )
        voice_id = settings.voice_profile or self.voice_id
        if not voice_id:
            raise ValueError('Hãy chọn voice profile/voice id trước khi generate audio qua HTTP provider.')
        text = (text or '').strip()
        if not text:
            raise ValueError('Không có nội dung văn bản để tạo voice.')
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'text': text,
            'voice_id': voice_id,
            'language': settings.language,
            'speed': float(settings.speed),
            'pitch': float(settings.pitch),
            'emotion': settings.emotion,
            'pause_ms': int(settings.pause_ms),
            'output_format': output_path.suffix.lower().lstrip('.'),
            'authorized': True,
            'clone_enabled': bool(settings.clone_enabled),
        }
        if settings.sample_path:
            sample = Path(settings.sample_path)
            validate_voice_sample(sample, ffmpeg_path=self.ffmpeg_path)
            payload['sample_audio_base64'] = base64.b64encode(sample.read_bytes()).decode('ascii')
            payload['sample_filename'] = sample.name
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['X-API-Key'] = self.api_key
        if progress_callback:
            progress_callback(15, 'Đang gửi yêu cầu tới HTTP voice provider…')
        response = requests.post(self.endpoint, json=payload, headers=headers, timeout=self.http_timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = response.text.strip()[:800]
            raise RuntimeError(f'HTTP voice provider trả lỗi: {detail or exc}') from exc
        content_type = (response.headers.get('content-type') or '').lower()
        if content_type.startswith('audio/') or content_type.startswith('application/octet-stream'):
            output_path.write_bytes(response.content)
        else:
            data = response.json()
            if data.get('audio_base64'):
                output_path.write_bytes(base64.b64decode(data['audio_base64']))
            else:
                raise RuntimeError(
                    'HTTP voice provider phải trả về audio binary hoặc JSON có trường audio_base64.'
                )
        if progress_callback:
            progress_callback(85, 'Đã nhận audio từ HTTP provider, đang kiểm tra output…')
        validate_audio_output(output_path, ffmpeg_path=self.ffmpeg_path)
        if progress_callback:
            progress_callback(100, f'Đã tạo audio: {output_path}')
        return output_path


class VoiceProvider:
    def __init__(
        self,
        endpoint='',
        api_key='',
        voice_id='',
        supports_segmented_srt=False,
        provider_type='http',
        ffmpeg_path='ffmpeg',
        http_timeout=90,
    ):
        self.provider_type = (provider_type or 'http').strip().lower()
        self._adapter = create_voice_adapter(
            self.provider_type,
            endpoint=endpoint,
            api_key=api_key,
            voice_id=voice_id,
            ffmpeg_path=ffmpeg_path,
            http_timeout=http_timeout,
        )
        self.capabilities = self._adapter.capabilities
        self.supports_segmented_srt = bool(supports_segmented_srt or self.capabilities.supports_segmented_srt)

    def configured(self):
        return self._adapter.configured()

    def generate(self, text, output_path, authorized=False, subtitles=None, settings=None, progress_callback=None):
        if subtitles and not self.supports_segmented_srt:
            raise NotImplementedError('Provider hiện tại chưa khai báo hỗ trợ render theo từng câu subtitle.')
        active_settings = settings or VoiceSettings(provider=self.provider_type, voice_profile=self._adapter.voice_id)
        active_settings.validate(ffmpeg_path=self._adapter.ffmpeg_path)
        if not self.configured():
            if self.provider_type == 'sapi':
                raise NotImplementedError(
                    'Provider local SAPI chưa sẵn sàng trong môi trường hiện tại. '
                    'Hãy chạy trên Windows hoặc chọn HTTP provider.'
                )
            raise NotImplementedError('Chưa cấu hình adapter TTS chính thức trong Settings hoặc biến môi trường.')
        return self._adapter.generate(
            text,
            output_path,
            settings=active_settings,
            authorized=authorized,
            progress_callback=progress_callback,
        )


class VoiceStudioService:
    def __init__(self, provider, ffmpeg_path='ffmpeg'):
        self.provider = provider
        self.ffmpeg_path = ffmpeg_path or 'ffmpeg'

    def generate_audio(
        self,
        text,
        output_path,
        settings,
        authorized=False,
        source_path='',
        preview=False,
        progress_callback=None,
        cancel_callback=None,
    ):
        settings.validate(ffmpeg_path=self.ffmpeg_path)
        source_path = (source_path or settings.text_source_path or '').strip()
        if preview:
            excerpt = load_preview_text(text, source_path)
            return self.provider.generate(
                excerpt,
                output_path,
                authorized=authorized,
                settings=settings,
                progress_callback=progress_callback,
            )
        if source_path.lower().endswith(('.srt', '.vtt')):
            segments = build_timed_segments(source_path, pause_ms=settings.pause_ms)
            return self.render_timed_audio(
                segments,
                output_path,
                settings,
                authorized=authorized,
                progress_callback=progress_callback,
                cancel_callback=cancel_callback,
            )
        content = load_text_content(text=text, source_path=source_path)
        return self.provider.generate(
            content,
            output_path,
            authorized=authorized,
            settings=settings,
            progress_callback=progress_callback,
        )

    def render_timed_audio(
        self,
        segments,
        output_path,
        settings,
        authorized=False,
        progress_callback=None,
        cancel_callback=None,
    ):
        if not segments:
            raise ValueError('Không có segment subtitle nào để render audio.')
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        warnings = []
        with tempfile.TemporaryDirectory(prefix='aiys-dub-') as temp_dir:
            temp_dir = Path(temp_dir)
            normalized_segments = []
            total = len(segments)
            for index, segment in enumerate(segments, 1):
                if cancel_callback:
                    cancel_callback()
                if progress_callback:
                    progress_callback(max(5, int(index * 45 / total)), f'Đang render segment {index}/{total}…')
                raw_path = temp_dir / f'segment_{index:04d}_raw.wav'
                normalized_path = temp_dir / f'segment_{index:04d}.wav'
                segment_settings = VoiceSettings(**{**asdict(settings), 'output_format': 'wav', 'pause_ms': 0})
                self.provider.generate(
                    segment.text,
                    raw_path,
                    authorized=authorized,
                    settings=segment_settings,
                    progress_callback=None,
                )
                normalize_audio_to_wav(raw_path, normalized_path, self.ffmpeg_path)
                fitted_path, actual_ms, warning = fit_audio_segment(
                    normalized_path,
                    segment.duration_ms,
                    settings.fit_strategy,
                    self.ffmpeg_path,
                    temp_dir / f'segment_{index:04d}_fit.wav',
                )
                if warning:
                    warnings.append(f'Segment {segment.index}: {warning}')
                normalized_segments.append((segment, fitted_path, actual_ms))
            if progress_callback:
                progress_callback(60, 'Đang ghép các segment theo timestamp…')
            final_wav = output_path if output_path.suffix.lower() == '.wav' else temp_dir / 'final_track.wav'
            compose_timed_track(normalized_segments, final_wav)
            validate_audio_output(final_wav, expect_extension='.wav', ffmpeg_path=self.ffmpeg_path)
            if output_path.suffix.lower() == '.mp3':
                if progress_callback:
                    progress_callback(80, 'Đang chuyển WAV sang MP3…')
                convert_audio_format(final_wav, output_path, self.ffmpeg_path)
                validate_audio_output(output_path, expect_extension='.mp3', ffmpeg_path=self.ffmpeg_path)
                final_path = output_path
            else:
                final_path = final_wav
        if progress_callback:
            message = f'Đã tạo track audio: {final_path}'
            if warnings:
                message += f' | Cảnh báo: {len(warnings)} segment cần chú ý.'
            progress_callback(100, message)
        return {'audio_path': Path(final_path), 'warnings': warnings}

    def dub_video(
        self,
        video_path,
        text,
        output_audio_path,
        output_video_path,
        settings,
        authorized=False,
        source_path='',
        progress_callback=None,
        cancel_callback=None,
    ):
        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f'Không tìm thấy video nguồn: {video_path}')
        source_path = (source_path or settings.text_source_path or '').strip()
        segments = build_timed_segments(source_path, text=text, pause_ms=settings.pause_ms)
        audio_result = self.render_timed_audio(
            segments,
            output_audio_path,
            settings,
            authorized=authorized,
            progress_callback=lambda percent, message: progress_callback(min(percent, 75), message) if progress_callback else None,
            cancel_callback=cancel_callback,
        )
        if cancel_callback:
            cancel_callback()
        if progress_callback:
            progress_callback(80, 'Đang mux audio mới vào video bằng FFmpeg…')
        assembler = VideoAssembler(self.ffmpeg_path)
        muxed_path = assembler.mux_audio(
            video_path,
            audio_result['audio_path'],
            output_video_path,
            progress_callback=lambda percent, message: progress_callback(80 + int(percent * 0.2), message) if progress_callback else None,
        )
        if progress_callback:
            progress_callback(100, f'Đã tạo video lồng tiếng: {muxed_path}')
        return {'audio_path': audio_result['audio_path'], 'video_path': muxed_path, 'warnings': audio_result['warnings']}


def create_voice_adapter(provider_type, **kwargs):
    provider_type = (provider_type or 'sapi').strip().lower()
    if provider_type == 'sapi':
        return SapiVoiceAdapter(**kwargs)
    if provider_type == 'http':
        return HttpVoiceAdapter(**kwargs)
    raise ValueError(f'Provider không được hỗ trợ: {provider_type}')


def ensure_voice_authorized(authorized, clone_enabled=False):
    if not authorized:
        if clone_enabled:
            raise PermissionError(
                'Voice cloning/chọn mẫu giọng chỉ được phép khi bạn xác nhận đang sở hữu hoặc có quyền sử dụng giọng đó.'
            )
        raise PermissionError('Voice/TTS chỉ được chạy khi bạn xác nhận đang sở hữu hoặc có quyền sử dụng voice đó.')
    return True


def validate_voice_sample(path, ffmpeg_path='ffmpeg', max_size_bytes=MAX_SAMPLE_BYTES, max_duration_ms=MAX_SAMPLE_DURATION_MS):
    sample = Path(path)
    if not sample.exists():
        raise FileNotFoundError(f'Không tìm thấy mẫu giọng: {sample}')
    if sample.suffix.lower() not in SUPPORTED_AUDIO_SAMPLE_EXTENSIONS:
        raise ValueError('Mẫu giọng chỉ hỗ trợ WAV/MP3/M4A/OGG/FLAC.')
    size_bytes = sample.stat().st_size
    if size_bytes <= 0:
        raise ValueError('Mẫu giọng đang rỗng.')
    if size_bytes > max_size_bytes:
        raise ValueError('Mẫu giọng vượt quá kích thước cho phép 15MB.')
    duration_ms = probe_audio_duration_ms(sample, ffmpeg_path=ffmpeg_path)
    if duration_ms is None:
        raise ValueError('Không xác định được thời lượng mẫu giọng. Hãy cài FFmpeg/ffprobe hoặc dùng file WAV.')
    if duration_ms > max_duration_ms:
        raise ValueError('Mẫu giọng vượt quá thời lượng cho phép 180 giây.')
    return VoiceSampleInfo(str(sample), sample.suffix.lower(), size_bytes, duration_ms)


def validate_audio_output(path, expect_extension='', ffmpeg_path='ffmpeg'):
    audio_path = Path(path)
    if not audio_path.exists():
        raise FileNotFoundError(f'Không tìm thấy file audio output: {audio_path}')
    if audio_path.stat().st_size <= 0:
        raise ValueError(f'File audio output đang rỗng: {audio_path}')
    if expect_extension and audio_path.suffix.lower() != expect_extension.lower():
        raise ValueError(f'Audio output phải có đuôi {expect_extension}, nhận được {audio_path.suffix}.')
    if audio_path.suffix.lower() not in {'.wav', '.mp3'}:
        raise ValueError('Audio output chỉ hỗ trợ WAV hoặc MP3.')
    duration_ms = probe_audio_duration_ms(audio_path, ffmpeg_path=ffmpeg_path)
    if audio_path.suffix.lower() == '.wav' and duration_ms is None:
        raise ValueError('Audio output có thời lượng không hợp lệ.')
    if duration_ms is not None and duration_ms <= 0:
        raise ValueError('Audio output có thời lượng không hợp lệ.')
    return True


def load_preview_text(text='', source_path=''):
    content = load_text_content(text=text, source_path=source_path)
    compact = re.sub(r'\s+', ' ', content).strip()
    preview = compact[:280].strip()
    if not preview:
        raise ValueError('Không có nội dung để preview voice.')
    return preview


def load_text_content(text='', source_path=''):
    source_path = str(source_path or '').strip()
    if source_path:
        path = Path(source_path)
        if not path.exists():
            raise FileNotFoundError(f'Không tìm thấy file nguồn: {path}')
        suffix = path.suffix.lower()
        if suffix == '.txt':
            content = path.read_text(encoding='utf-8').strip()
            if not content:
                raise ValueError('File TXT không có nội dung.')
            return content
        if suffix in {'.srt', '.vtt'}:
            cues = parse_subtitle_file(path)
            return '\n'.join(cue.text for cue in cues)
        raise ValueError('Chỉ hỗ trợ nguồn văn bản .txt, .srt hoặc .vtt.')
    content = (text or '').strip()
    if not content:
        raise ValueError('Hãy nhập text hoặc chọn file .txt/.srt/.vtt.')
    return content


def build_timed_segments(source_path='', text='', pause_ms=150, max_chars=160):
    source_path = str(source_path or '').strip()
    if source_path:
        path = Path(source_path)
        suffix = path.suffix.lower()
        if suffix in {'.srt', '.vtt'}:
            cues = parse_subtitle_file(path)
            segments = []
            for cue in cues:
                segments.extend(split_cue_into_segments(cue, max_chars=max_chars))
            return segments
        if suffix == '.txt':
            return build_segments_from_plain_text(path.read_text(encoding='utf-8'), pause_ms=pause_ms, max_chars=max_chars)
        raise ValueError('Chỉ hỗ trợ file .txt, .srt hoặc .vtt cho voice dubbing.')
    if not (text or '').strip():
        raise ValueError('Thiếu nguồn text/subtitle để tạo dubbing.')
    return build_segments_from_plain_text(text, pause_ms=pause_ms, max_chars=max_chars)


def split_cue_into_segments(cue: SubtitleCue, max_chars=160):
    fragments = split_text_fragments(cue.text, max_chars=max_chars)
    if len(fragments) == 1:
        return [TimedSegment(cue.index, cue.start_ms, cue.end_ms, fragments[0])]
    total_weight = sum(max(len(fragment.strip()), 1) for fragment in fragments)
    cue_duration_ms = max(cue.end_ms - cue.start_ms, 0)
    cursor = cue.start_ms
    segments = []
    for index, fragment in enumerate(fragments, 1):
        remaining = cue.end_ms - cursor
        if index == len(fragments):
            end_ms = cue.end_ms
        else:
            weight = max(len(fragment.strip()), 1)
            duration = max(int(cue_duration_ms * (weight / total_weight)), 350)
            duration = min(duration, max(remaining - (len(fragments) - index) * 350, 350))
            end_ms = min(cursor + duration, cue.end_ms)
        segments.append(TimedSegment(int(f'{cue.index}{index}'), cursor, end_ms, fragment))
        cursor = end_ms
    return segments


def split_text_fragments(text, max_chars=160):
    raw_parts = []
    for line in text.splitlines():
        raw_parts.extend(re.split(r'(?<=[.!?…])\s+', line.strip()))
    fragments = []
    for part in raw_parts:
        part = re.sub(r'\s+', ' ', part or '').strip()
        if not part:
            continue
        if len(part) <= max_chars:
            fragments.append(part)
        else:
            fragments.extend(split_script_lines(part, max_chars=max_chars))
    return fragments or ['']


def build_segments_from_plain_text(text, pause_ms=150, max_chars=160):
    fragments = split_text_fragments(text, max_chars=max_chars)
    segments = []
    cursor = 0
    for index, fragment in enumerate(fragments, 1):
        words = max(len(fragment.split()), 1)
        duration = max(1_200, int((words / 2.6) * 1000))
        start_ms = cursor
        end_ms = start_ms + duration
        segments.append(TimedSegment(index, start_ms, end_ms, fragment))
        cursor = end_ms + max(int(pause_ms), 0)
    return segments


def compose_timed_track(items, output_path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    first_path = Path(items[0][1])
    with wave.open(str(first_path), 'rb') as first_wave:
        params = first_wave.getparams()
    sample_rate = params.framerate
    channels = params.nchannels
    sample_width = params.sampwidth
    bytes_per_frame = channels * sample_width
    cursor_ms = 0
    with wave.open(str(output_path), 'wb') as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width)
        writer.setframerate(sample_rate)
        for segment, segment_path, actual_ms in items:
            if segment.start_ms > cursor_ms:
                writer.writeframes(make_silence_frames(segment.start_ms - cursor_ms, sample_rate, bytes_per_frame))
                cursor_ms = segment.start_ms
            with wave.open(str(segment_path), 'rb') as segment_wave:
                writer.writeframes(segment_wave.readframes(segment_wave.getnframes()))
            cursor_ms = segment.start_ms + actual_ms
            if actual_ms < segment.duration_ms:
                writer.writeframes(make_silence_frames(segment.duration_ms - actual_ms, sample_rate, bytes_per_frame))
                cursor_ms = segment.end_ms


def make_silence_frames(duration_ms, sample_rate, bytes_per_frame):
    frame_count = max(int(round(sample_rate * (duration_ms / 1000.0))), 0)
    return b'\x00' * frame_count * bytes_per_frame


def normalize_audio_to_wav(input_path, output_path, ffmpeg_path='ffmpeg'):
    input_path = Path(input_path)
    output_path = Path(output_path)
    if shutil.which(ffmpeg_path) is None and not Path(ffmpeg_path).exists() and input_path.suffix.lower() != '.wav':
        raise RuntimeError('Cần FFmpeg để chuẩn hoá audio không phải WAV.')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if input_path.suffix.lower() == '.wav' and (Path(ffmpeg_path).exists() or shutil.which(ffmpeg_path)):
        cmd = [
            ffmpeg_path,
            '-y',
            '-i',
            str(input_path),
            '-ar',
            str(DEFAULT_SAMPLE_RATE),
            '-ac',
            str(DEFAULT_CHANNELS),
            '-c:a',
            'pcm_s16le',
            str(output_path),
        ]
        run_command(cmd, 'Chuẩn hoá WAV bằng FFmpeg thất bại.')
        return output_path
    if input_path.suffix.lower() == '.wav':
        shutil.copyfile(input_path, output_path)
        return output_path
    cmd = [
        ffmpeg_path,
        '-y',
        '-i',
        str(input_path),
        '-ar',
        str(DEFAULT_SAMPLE_RATE),
        '-ac',
        str(DEFAULT_CHANNELS),
        '-c:a',
        'pcm_s16le',
        str(output_path),
    ]
    run_command(cmd, 'Chuẩn hoá audio bằng FFmpeg thất bại.')
    return output_path


def convert_audio_format(input_path, output_path, ffmpeg_path='ffmpeg'):
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if input_path.suffix.lower() == output_path.suffix.lower():
        shutil.copyfile(input_path, output_path)
        return output_path
    if shutil.which(ffmpeg_path) is None and not Path(ffmpeg_path).exists():
        raise RuntimeError('Cần FFmpeg để chuyển đổi giữa WAV và MP3.')
    codec = 'libmp3lame' if output_path.suffix.lower() == '.mp3' else 'pcm_s16le'
    cmd = [ffmpeg_path, '-y', '-i', str(input_path), '-c:a', codec, str(output_path)]
    run_command(cmd, 'FFmpeg chuyển đổi audio thất bại.')
    return output_path


def fit_audio_segment(input_path, target_ms, strategy, ffmpeg_path, output_path):
    input_path = Path(input_path)
    actual_ms = probe_audio_duration_ms(input_path, ffmpeg_path=ffmpeg_path)
    if actual_ms is None:
        return input_path, target_ms, 'không xác định được thời lượng segment nên không thể fit.'
    if actual_ms <= target_ms or target_ms <= 0:
        return input_path, actual_ms, None
    output_path = Path(output_path)
    warning = f'audio dài hơn timestamp ({actual_ms}ms > {target_ms}ms).'
    if strategy == 'warn':
        return input_path, actual_ms, warning
    if shutil.which(ffmpeg_path) is None and not Path(ffmpeg_path).exists():
        return input_path, actual_ms, warning + ' FFmpeg chưa sẵn sàng để speed/trim.'
    if strategy == 'trim':
        cmd = [ffmpeg_path, '-y', '-i', str(input_path), '-t', f'{target_ms / 1000:.3f}', '-c:a', 'pcm_s16le', str(output_path)]
        run_command(cmd, 'FFmpeg trim audio thất bại.')
        return output_path, min(target_ms, actual_ms), warning + ' Đã trim an toàn về đúng độ dài.'
    ratio = actual_ms / target_ms
    filters = []
    while ratio > 2.0:
        filters.append('atempo=2.0')
        ratio /= 2.0
    filters.append(f'atempo={ratio:.5f}')
    cmd = [
        ffmpeg_path,
        '-y',
        '-i',
        str(input_path),
        '-filter:a',
        ','.join(filters),
        '-c:a',
        'pcm_s16le',
        str(output_path),
    ]
    run_command(cmd, 'FFmpeg speed-adjust audio thất bại.')
    return output_path, probe_audio_duration_ms(output_path, ffmpeg_path=ffmpeg_path) or target_ms, warning + ' Đã fit bằng speed adjustment.'


def probe_audio_duration_ms(path, ffmpeg_path='ffmpeg'):
    audio_path = Path(path)
    if not audio_path.exists():
        return None
    if audio_path.suffix.lower() == '.wav':
        try:
            with contextlib.closing(wave.open(str(audio_path), 'rb')) as handle:
                frames = handle.getnframes()
                rate = handle.getframerate() or 1
                return int((frames / rate) * 1000)
        except (wave.Error, EOFError):
            return None
    ffprobe = resolve_ffprobe(ffmpeg_path)
    if not ffprobe:
        return None
    command = [
        ffprobe,
        '-v',
        'error',
        '-show_entries',
        'format=duration',
        '-of',
        'default=noprint_wrappers=1:nokey=1',
        str(audio_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if completed.returncode != 0:
        return None
    try:
        return int(float((completed.stdout or '0').strip()) * 1000)
    except ValueError:
        return None


def resolve_ffprobe(ffmpeg_path='ffmpeg'):
    ffmpeg_bin = Path(ffmpeg_path)
    if ffmpeg_bin.exists():
        sibling = ffmpeg_bin.with_name('ffprobe')
        if sibling.exists():
            return str(sibling)
        sibling_exe = ffmpeg_bin.with_name('ffprobe.exe')
        if sibling_exe.exists():
            return str(sibling_exe)
    return shutil.which('ffprobe') or shutil.which('ffprobe.exe')


def run_command(command, error_message):
    completed = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or '').strip()
        raise RuntimeError(f'{error_message} {detail}'.strip())
    return completed
