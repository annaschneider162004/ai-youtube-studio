import tempfile
import unittest
import wave
from pathlib import Path

from app.services.voice import (
    VoiceSettings,
    build_timed_segments,
    ensure_voice_authorized,
    validate_audio_output,
    validate_voice_sample,
)


class VoiceServiceTests(unittest.TestCase):
    def _write_wav(self, path, duration_ms=500):
        frame_rate = 16000
        frame_count = int(frame_rate * (duration_ms / 1000))
        with wave.open(str(path), 'wb') as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(frame_rate)
            handle.writeframes(b'\x00\x00' * frame_count)

    def test_voice_settings_require_sample_for_cloning(self):
        with self.assertRaisesRegex(ValueError, 'yêu cầu upload mẫu giọng'):
            VoiceSettings(clone_enabled=True).validate()

    def test_authorization_gate_blocks_unauthorized_cloning(self):
        with self.assertRaisesRegex(PermissionError, 'Voice cloning'):
            ensure_voice_authorized(False, clone_enabled=True)

    def test_validate_voice_sample_returns_duration_for_wav(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sample = Path(temp_dir) / 'sample.wav'
            self._write_wav(sample, duration_ms=1200)
            info = validate_voice_sample(sample)
            self.assertEqual('.wav', info.extension)
            self.assertGreaterEqual(info.duration_ms, 1100)

    def test_build_timed_segments_from_srt_preserves_timeline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            subtitle = Path(temp_dir) / 'sample.srt'
            subtitle.write_text(
                '1\n00:00:00,000 --> 00:00:04,000\nXin chào. Đây là câu dài để tách nhỏ.\n\n'
                '2\n00:00:05,000 --> 00:00:07,000\nKết thúc.\n',
                encoding='utf-8',
            )
            segments = build_timed_segments(subtitle)
            self.assertGreaterEqual(len(segments), 3)
            self.assertEqual(0, segments[0].start_ms)
            self.assertEqual(7000, segments[-1].end_ms)
            self.assertTrue(all(segment.end_ms > segment.start_ms for segment in segments))

    def test_validate_audio_output_rejects_empty_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / 'empty.wav'
            audio.write_bytes(b'')
            with self.assertRaisesRegex(ValueError, 'đang rỗng'):
                validate_audio_output(audio, expect_extension='.wav')

    def test_validate_audio_output_rejects_invalid_wav_header(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio = Path(temp_dir) / 'invalid.wav'
            audio.write_bytes(b'not-a-real-wav')
            with self.assertRaisesRegex(ValueError, 'thời lượng không hợp lệ'):
                validate_audio_output(audio, expect_extension='.wav')


if __name__ == '__main__':
    unittest.main()
