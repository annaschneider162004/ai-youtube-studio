from difflib import SequenceMatcher
from pathlib import Path
import re


BLOCK_PATTERNS = [
    r'\bfake\s+(views?|likes?|subscribers?|comments?)\b',
    r'\bbuy\s+(views?|likes?|subscribers?|comments?)\b',
    r'\bbypass\b.*\b(captcha|limit|restriction|ban|detection)\b',
    r'\bevade\b.*\b(restriction|ban|detection)\b',
]

ALLOWED_THUMBNAIL_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp'}
ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv'}


def _check_file(path_value, allowed_extensions, label):
    if not path_value:
        return [f'Chưa chọn {label}.']
    path = Path(path_value)
    if not path.exists():
        return [f'{label} không tồn tại: {path}']
    if path.suffix.lower() not in allowed_extensions:
        return [f'{label} phải có định dạng {", ".join(sorted(allowed_extensions))}.']
    return []


def review(
    title,
    description='',
    recent_titles=None,
    duplicate_threshold=0.88,
    voice_authorized=False,
    media_authorized=False,
    thumbnail_path='',
    video_path='',
    privacy='private',
    publish_at=None,
):
    issues = []
    warnings = []
    text = (title or '') + '\n' + (description or '')
    for pattern in BLOCK_PATTERNS:
        if re.search(pattern, text, re.I):
            issues.append('Phát hiện ngôn ngữ bị chặn: fake engagement hoặc né enforcement.')
    if not 3 <= len((title or '').strip()) <= 100:
        warnings.append('Tiêu đề nên dài từ 3 đến 100 ký tự.')
    if len((description or '').strip()) < 10:
        warnings.append('Mô tả quá ngắn; nên bổ sung ngữ cảnh trước khi publish.')
    for old in recent_titles or []:
        normalized_old = (old or '').strip().lower()
        normalized_title = (title or '').strip().lower()
        if not normalized_old or not normalized_title:
            continue
        score = SequenceMatcher(None, normalized_title, normalized_old).ratio()
        if normalized_title == normalized_old:
            issues.append('Tiêu đề trùng với project/video đã có trong cơ sở dữ liệu.')
        elif score >= duplicate_threshold:
            warnings.append(f'Tiêu đề rất giống nội dung đã có ({score:.0%}).')
    if not voice_authorized:
        issues.append('Chưa xác nhận quyền sử dụng voice/TTS cho project này.')
    if not media_authorized:
        issues.append('Chưa xác nhận quyền sử dụng media nguồn cho project này.')
    warnings.extend(_check_file(thumbnail_path, ALLOWED_THUMBNAIL_EXTENSIONS, 'thumbnail') if thumbnail_path else [])
    warnings.extend(_check_file(video_path, ALLOWED_VIDEO_EXTENSIONS, 'video') if video_path else [])
    if publish_at and privacy == 'public':
        warnings.append('Video có lịch publish nên upload private trước rồi mới publishAt.')
    return {'ok': not issues, 'blocked': bool(issues), 'issues': issues, 'warnings': warnings}
