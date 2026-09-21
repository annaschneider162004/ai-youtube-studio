from pathlib import Path


class VoiceProvider:
    def __init__(self, endpoint='', api_key='', voice_id='', supports_segmented_srt=False):
        self.endpoint = endpoint
        self.api_key = api_key
        self.voice_id = voice_id
        self.supports_segmented_srt = supports_segmented_srt

    def configured(self):
        return bool(self.endpoint and self.voice_id)

    def generate(self, text, output_path, authorized=False, subtitles=None):
        if not authorized:
            raise PermissionError('Voice/TTS chỉ được chạy khi bạn xác nhận đang sở hữu hoặc có quyền sử dụng voice đó.')
        if subtitles and not self.supports_segmented_srt:
            raise NotImplementedError('Provider hiện tại chưa khai báo hỗ trợ render theo từng câu subtitle.')
        if not self.configured():
            raise NotImplementedError('Chưa cấu hình adapter TTS chính thức trong Settings hoặc biến môi trường.')
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        raise NotImplementedError('Cần API contract/credential thật của provider để tạo audio. V5 chỉ cung cấp adapter an toàn, không giả lập provider.')
