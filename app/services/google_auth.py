import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid',
]

class GoogleAuth:
    def __init__(self, path='data/client_secret.json'):
        self.path = path

    def login(self):
        p = Path(self.path)
        if not p.exists():
            raise FileNotFoundError(f'Missing OAuth client file: {p}')
        flow = InstalledAppFlow.from_client_secrets_file(str(p), SCOPES)
        creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')
        yt = build('youtube', 'v3', credentials=creds)
        data = yt.channels().list(part='snippet,statistics,contentDetails', mine=True).execute()
        if not data.get('items'):
            raise RuntimeError('No YouTube channel found for this Google account.')
        ch = data['items'][0]
        email = 'Google account'
        try:
            user = build('oauth2', 'v2', credentials=creds).userinfo().get().execute()
            email = user.get('email') or email
        except Exception:
            pass
        token = {
            'token': creds.token, 'refresh_token': creds.refresh_token,
            'token_uri': creds.token_uri, 'client_id': creds.client_id,
            'client_secret': creds.client_secret, 'scopes': list(creds.scopes or SCOPES)
        }
        return {'email': email, 'channel_id': ch['id'], 'channel_title': ch['snippet']['title'], 'token_json': json.dumps(token)}
