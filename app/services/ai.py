import json, urllib.request

class AIProvider:
    def __init__(self, endpoint='', api_key='', model=''):
        self.endpoint, self.api_key, self.model = endpoint, api_key, model

    def generate_script(self, topic, language='English'):
        if not self.endpoint:
            return (f'HOOK: {topic}\n\nINTRO: Today we explore {topic}.\n\nMAIN: Build an original, useful story around the topic with clear sections, examples and a satisfying progression.\n\nENDING: Summarize the key point and invite viewers to watch the next episode.')
        payload = {'model': self.model, 'topic': topic, 'language': language, 'task': 'Write an original YouTube script. Return plain text.'}
        req = urllib.request.Request(self.endpoint, data=json.dumps(payload).encode(), headers={'Content-Type':'application/json','Authorization':f'Bearer {self.api_key}'} if self.api_key else {'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=60) as r:
            data=json.loads(r.read().decode())
        return data.get('text') or data.get('content') or data.get('output') or str(data)

    def generate_title_ideas(self, topic):
        return [f'{topic} Explained', f'The Story of {topic}', f'What Happens in {topic}?']
