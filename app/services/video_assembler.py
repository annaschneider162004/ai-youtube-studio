import shutil, subprocess
from pathlib import Path

class VideoAssembler:
    @staticmethod
    def available(): return shutil.which('ffmpeg') is not None

    def assemble(self, image_path, voice_path, output_path, subtitles=None):
        if not self.available(): raise RuntimeError('FFmpeg is not installed or not on PATH.')
        cmd=['ffmpeg','-y','-loop','1','-i',str(image_path),'-i',str(voice_path)]
        if subtitles: cmd += ['-vf', f"subtitles={str(subtitles).replace('\\','/')}"]
        cmd += ['-c:v','libx264','-tune','stillimage','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(output_path)]
        subprocess.run(cmd, check=True)
        return Path(output_path)
