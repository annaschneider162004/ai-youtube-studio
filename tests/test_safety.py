import unittest

from app.services.safety import review


class SafetyTests(unittest.TestCase):
    def test_blocks_unsafe_and_missing_rights(self):
        result = review(
            'Buy views fast',
            'description',
            recent_titles=['Safe title'],
            voice_authorized=False,
            media_authorized=False,
        )
        self.assertTrue(result['blocked'])
        self.assertTrue(any('ngôn ngữ bị chặn' in item for item in result['issues']))
        self.assertTrue(any('voice/TTS' in item for item in result['issues']))

    def test_warns_on_duplicate_title(self):
        result = review(
            'How AI works',
            'A meaningful description',
            recent_titles=['How AI works'],
            voice_authorized=True,
            media_authorized=True,
        )
        self.assertTrue(result['blocked'])
        self.assertTrue(any('trùng' in item for item in result['issues']))


if __name__ == '__main__':
    unittest.main()
