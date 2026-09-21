import json
import urllib.request


class AIProvider:
    def __init__(self, endpoint='', api_key='', model=''):
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model

    def generate_script(self, topic, language='English'):
        if not self.endpoint:
            return (
                f'HOOK: {topic}\n\n'
                f'INTRO: Today we explore {topic}.\n\n'
                'MAIN: Build an original, useful story around the topic with clear sections, examples '
                'and a satisfying progression.\n\n'
                'ENDING: Summarize the key point and invite viewers to watch the next episode.'
            )
        payload = {
            'model': self.model,
            'topic': topic,
            'language': language,
            'task': 'Write an original YouTube script. Return plain text.',
        }
        headers = {'Content-Type': 'application/json'}
        if self.api_key:
            headers['Authorization'] = '******'
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload).encode(),
            headers=headers,
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode())
        return data.get('text') or data.get('content') or data.get('output') or str(data)

    def generate_title_ideas(self, topic):
        return [f'{topic} Explained', f'The Story of {topic}', f'What Happens in {topic}?']
