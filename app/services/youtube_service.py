import json
from pathlib import Path


class YouTubeService:
    def __init__(self, token_json):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        data = json.loads(token_json)
        creds = Credentials(
            token=data.get('token'),
            refresh_token=data.get('refresh_token'),
            token_uri=data.get('token_uri'),
            client_id=data.get('client_id'),
            client_secret=data.get('client_secret'),
            scopes=data.get('scopes'),
        )
        self.yt = build('youtube', 'v3', credentials=creds)

    def channel(self):
        data = self.yt.channels().list(part='snippet,statistics,contentDetails', mine=True).execute()
        return data.get('items', [None])[0]

    def uploads(self, limit=20):
        channel = self.channel()
        if not channel:
            return []
        playlist_id = channel['contentDetails']['relatedPlaylists']['uploads']
        return self.yt.playlistItems().list(
            part='snippet,contentDetails',
            playlistId=playlist_id,
            maxResults=min(limit, 50),
        ).execute().get('items', [])

    def upload(self, file_path, title, description='', tags=None, privacy='private', publish_at=None, category_id='22', progress_callback=None):
        from googleapiclient.http import MediaFileUpload

        if not Path(file_path).exists():
            raise FileNotFoundError(f'Không tìm thấy file video để upload: {file_path}')
        if publish_at and privacy == 'public':
            raise ValueError('Video có lịch publish phải upload dạng private/unlisted rồi mới đặt publishAt hợp lệ.')
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags or [],
                'categoryId': category_id,
            },
            'status': {'privacyStatus': 'private' if publish_at else privacy},
        }
        if publish_at:
            body['status']['publishAt'] = publish_at
        request = self.yt.videos().insert(
            part='snippet,status',
            body=body,
            media_body=MediaFileUpload(file_path, chunksize=8 * 1024 * 1024, resumable=True),
        )
        response = None
        attempt = 0
        while response is None:
            status, response = request.next_chunk()
            attempt += 1
            if progress_callback and status is not None:
                progress_callback(int(status.progress() * 100), f'Đang upload lên YouTube… ({attempt})')
        if progress_callback:
            progress_callback(100, f'Upload hoàn tất. Video ID: {response.get("id", "")}')
        return response

    def analytics_snapshot(self):
        channel = self.channel()
        if not channel:
            raise RuntimeError('Không tìm thấy channel YouTube cho token hiện tại.')
        stats = channel.get('statistics', {})
        return {
            'channel_id': channel['id'],
            'views': int(stats.get('viewCount', 0)),
            'subscribers': int(stats.get('subscriberCount', 0)),
            'video_count': int(stats.get('videoCount', 0)),
            'title': channel['snippet']['title'],
        }
