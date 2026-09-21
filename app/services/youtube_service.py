import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

class YouTubeService:
    def __init__(self, token_json):
        d = json.loads(token_json)
        creds = Credentials(token=d.get('token'), refresh_token=d.get('refresh_token'), token_uri=d.get('token_uri'), client_id=d.get('client_id'), client_secret=d.get('client_secret'), scopes=d.get('scopes'))
        self.yt = build('youtube', 'v3', credentials=creds)

    def channel(self):
        data = self.yt.channels().list(part='snippet,statistics,contentDetails', mine=True).execute()
        return data.get('items', [None])[0]

    def uploads(self, limit=20):
        ch = self.channel()
        if not ch: return []
        playlist_id = ch['contentDetails']['relatedPlaylists']['uploads']
        return self.yt.playlistItems().list(part='snippet,contentDetails', playlistId=playlist_id, maxResults=min(limit,50)).execute().get('items', [])

    def upload(self, file_path, title, description='', tags=None, privacy='private', publish_at=None, category_id='22'):
        body = {'snippet': {'title': title, 'description': description, 'tags': tags or [], 'categoryId': category_id}, 'status': {'privacyStatus': 'private' if publish_at else privacy}}
        if publish_at:
            body['status']['publishAt'] = publish_at
        req = self.yt.videos().insert(part='snippet,status', body=body, media_body=MediaFileUpload(file_path, chunksize=8*1024*1024, resumable=True))
        response = None
        while response is None:
            _, response = req.next_chunk()
        return response

    def analytics_snapshot(self):
        ch = self.channel()
        if not ch: raise RuntimeError('No channel found')
        stats = ch.get('statistics', {})
        return {'channel_id': ch['id'], 'views': int(stats.get('viewCount', 0)), 'subscribers': int(stats.get('subscriberCount', 0)), 'video_count': int(stats.get('videoCount', 0)), 'title': ch['snippet']['title']}
