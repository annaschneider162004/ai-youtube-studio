import tempfile
import unittest
from pathlib import Path

from app.services.subtitles import format_timestamp, make_srt, parse_srt, parse_vtt


class SubtitleTests(unittest.TestCase):
    def test_make_and_parse_srt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / 'sample.srt'
            make_srt('Xin chào\nĐây là test', path, seconds_per_line=3)
            cues = parse_srt(path.read_text(encoding='utf-8'))
            self.assertEqual(2, len(cues))
            self.assertEqual('Xin chào', cues[0].text)
            self.assertEqual('00:00:03,000', format_timestamp(cues[0].end_ms))

    def test_parse_vtt(self):
        cues = parse_vtt(
            'WEBVTT\n\n'
            '00:00:00.000 --> 00:00:02.000\n'
            'Line 1\n\n'
            '00:00:02.500 --> 00:00:04.000\n'
            'Line 2\n'
        )
        self.assertEqual(2, len(cues))
        self.assertEqual('Line 2', cues[1].text)

    def test_invalid_overlap_raises(self):
        with self.assertRaisesRegex(ValueError, 'chồng timestamp'):
            parse_srt(
                '1\n00:00:00,000 --> 00:00:02,000\nA\n\n'
                '2\n00:00:01,500 --> 00:00:03,000\nB\n'
            )


if __name__ == '__main__':
    unittest.main()
