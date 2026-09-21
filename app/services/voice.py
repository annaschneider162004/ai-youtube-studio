from pathlib import Path
class VoiceProvider:
    def generate(self, text, output_path, authorized=False):
        if not authorized: raise PermissionError('Voice generation requires confirmation that you own or are authorized to use the voice.')
        raise NotImplementedError('Connect an official TTS/voice provider adapter in Settings.')
