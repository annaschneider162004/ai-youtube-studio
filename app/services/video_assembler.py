import shutil
import subprocess
from pathlib import Path


class VideoAssembler:
    def __init__(self, ffmpeg_path='ffmpeg'):
        self.ffmpeg_path = ffmpeg_path or 'ffmpeg'

    def available(self):
        if Path(self.ffmpeg_path).exists():
            return True
        return shutil.which(self.ffmpeg_path) is not None

    def validate(self, image_path, voice_path, output_path, subtitles=None):
        if not self.available():
            raise RuntimeError('FFmpeg chưa được cài hoặc đường dẫn FFmpeg không đúng.')
        image = Path(image_path)
        voice = Path(voice_path)
        output = Path(output_path)
        if not image.exists():
            raise FileNotFoundError(f'Không tìm thấy file hình/visual: {image}')
        if not voice.exists():
            raise FileNotFoundError(f'Không tìm thấy file voice/audio: {voice}')
        if subtitles and not Path(subtitles).exists():
            raise FileNotFoundError(f'Không tìm thấy subtitle: {subtitles}')
        if output.suffix.lower() not in {'.mp4', '.mov', '.mkv'}:
            raise ValueError('Output video phải có phần mở rộng .mp4, .mov hoặc .mkv.')
        output.parent.mkdir(parents=True, exist_ok=True)

    def _run_ffmpeg(self, cmd, progress_callback=None, start_message='Đang chạy FFmpeg…', success_message='FFmpeg hoàn tất.'):
        if progress_callback:
            progress_callback(5, start_message)
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
        )
        last_message = ''
        for raw in process.stdout or []:
            line = raw.strip()
            if not line:
                continue
            if line.startswith('out_time_ms='):
                if progress_callback:
                    progress_callback(75, 'FFmpeg đang xử lý media…')
            elif line.startswith('progress='):
                last_message = line.split('=', 1)[-1]
            elif progress_callback:
                progress_callback(30, line)
        code = process.wait()
        if code != 0:
            raise RuntimeError(f'FFmpeg thất bại ({code}). {last_message}'.strip())
        if progress_callback:
            progress_callback(100, success_message)

    def assemble(self, image_path, voice_path, output_path, subtitles=None, progress_callback=None):
        self.validate(image_path, voice_path, output_path, subtitles)
        cmd = [self.ffmpeg_path, '-y', '-loop', '1', '-i', str(image_path), '-i', str(voice_path)]
        if subtitles:
            subtitle_filter = f"subtitles={str(subtitles).replace(chr(92), '/')}"
            cmd += ['-vf', subtitle_filter]
        cmd += [
            '-c:v',
            'libx264',
            '-tune',
            'stillimage',
            '-pix_fmt',
            'yuv420p',
            '-c:a',
            'aac',
            '-shortest',
            '-progress',
            'pipe:1',
            '-nostats',
            str(output_path),
        ]
        self._run_ffmpeg(
            cmd,
            progress_callback=progress_callback,
            start_message='Bắt đầu ghép video bằng FFmpeg…',
            success_message=f'Đã tạo video: {output_path}',
        )
        return Path(output_path)

    def mux_audio(self, video_path, audio_path, output_path, progress_callback=None):
        if not self.available():
            raise RuntimeError('FFmpeg chưa được cài hoặc đường dẫn FFmpeg không đúng.')
        video = Path(video_path)
        audio = Path(audio_path)
        output = Path(output_path)
        if not video.exists():
            raise FileNotFoundError(f'Không tìm thấy video nguồn: {video}')
        if not audio.exists():
            raise FileNotFoundError(f'Không tìm thấy audio nguồn: {audio}')
        if output.suffix.lower() not in {'.mp4', '.mov', '.mkv'}:
            raise ValueError('Output video phải có phần mở rộng .mp4, .mov hoặc .mkv.')
        output.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg_path,
            '-y',
            '-i',
            str(video),
            '-i',
            str(audio),
            '-map',
            '0',
            '-map',
            '-0:a',
            '-map',
            '1:a:0',
            '-map_metadata',
            '0',
            '-c',
            'copy',
            '-c:a',
            'aac',
            '-shortest',
            '-progress',
            'pipe:1',
            '-nostats',
            str(output),
        ]
        self._run_ffmpeg(
            cmd,
            progress_callback=progress_callback,
            start_message='Đang mux voice track vào video…',
            success_message=f'Đã xuất video lồng tiếng: {output}',
        )
        return output
