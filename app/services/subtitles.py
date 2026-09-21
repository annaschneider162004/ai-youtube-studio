from dataclasses import dataclass
from pathlib import Path
import re


TIMESTAMP_RE = re.compile(r'^(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{3})$')


@dataclass(frozen=True)
class SubtitleCue:
    index: int
    start_ms: int
    end_ms: int
    text: str


def parse_timestamp(value):
    match = TIMESTAMP_RE.match(value.strip())
    if not match:
        raise ValueError(f'Timestamp không hợp lệ: {value}')
    parts = {key: int(raw) for key, raw in match.groupdict().items()}
    return ((parts['h'] * 60 + parts['m']) * 60 + parts['s']) * 1000 + parts['ms']


def format_timestamp(milliseconds, separator=','):
    milliseconds = max(int(milliseconds), 0)
    total_seconds, ms = divmod(milliseconds, 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{ms:03d}'


def split_script_lines(text, max_chars=72):
    lines = []
    for raw in [part.strip() for part in text.splitlines() if part.strip()]:
        if len(raw) <= max_chars:
            lines.append(raw)
            continue
        words = raw.split()
        current = []
        for word in words:
            candidate = ' '.join(current + [word]).strip()
            if current and len(candidate) > max_chars:
                lines.append(' '.join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            lines.append(' '.join(current))
    return lines


def make_srt(text, output_path, seconds_per_line=4):
    lines = split_script_lines(text)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', encoding='utf-8', newline='\n') as handle:
        for i, line in enumerate(lines, 1):
            start_ms = (i - 1) * seconds_per_line * 1000
            end_ms = i * seconds_per_line * 1000
            handle.write(
                f'{i}\n'
                f'{format_timestamp(start_ms)} --> {format_timestamp(end_ms)}\n'
                f'{line}\n\n'
            )
    return str(output_path)


def parse_srt(text):
    blocks = re.split(r'\n\s*\n', text.strip(), flags=re.MULTILINE)
    cues = []
    for block in blocks:
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            raise ValueError(f'Khối SRT không hợp lệ: {block}')
        try:
            index = int(lines[0].strip())
        except ValueError as exc:
            raise ValueError(f'Số thứ tự SRT không hợp lệ: {lines[0]}') from exc
        if '-->' not in lines[1]:
            raise ValueError(f'Dòng timecode SRT không hợp lệ: {lines[1]}')
        start_raw, end_raw = [part.strip() for part in lines[1].split('-->', 1)]
        cue = SubtitleCue(
            index=index,
            start_ms=parse_timestamp(start_raw),
            end_ms=parse_timestamp(end_raw),
            text='\n'.join(lines[2:]).strip(),
        )
        cues.append(cue)
    validate_cues(cues)
    return cues


def parse_vtt(text):
    lines = [line.rstrip('\ufeff') for line in text.splitlines()]
    if not lines or not lines[0].strip().startswith('WEBVTT'):
        raise ValueError('Thiếu header WEBVTT.')
    body = '\n'.join(lines[1:]).strip()
    blocks = re.split(r'\n\s*\n', body, flags=re.MULTILINE)
    cues = []
    index = 1
    for block in blocks:
        parts = [line.rstrip() for line in block.splitlines() if line.strip()]
        if not parts:
            continue
        if '-->' not in parts[0]:
            parts = parts[1:]
        if not parts or '-->' not in parts[0]:
            raise ValueError(f'Khối VTT không hợp lệ: {block}')
        start_raw, end_raw = [part.strip() for part in parts[0].replace('.', ',').split('-->', 1)]
        cues.append(
            SubtitleCue(
                index=index,
                start_ms=parse_timestamp(start_raw),
                end_ms=parse_timestamp(end_raw),
                text='\n'.join(parts[1:]).strip(),
            )
        )
        index += 1
    validate_cues(cues)
    return cues


def parse_subtitle_file(path):
    path = Path(path)
    text = path.read_text(encoding='utf-8')
    suffix = path.suffix.lower()
    if suffix == '.srt':
        return parse_srt(text)
    if suffix == '.vtt':
        return parse_vtt(text)
    raise ValueError(f'Chỉ hỗ trợ file .srt hoặc .vtt, nhận được: {path.suffix}')


def validate_cues(cues, max_gap_ms=12_000):
    if not cues:
        raise ValueError('Không có subtitle để xử lý.')
    previous_end = None
    for cue in cues:
        if not cue.text.strip():
            raise ValueError(f'Subtitle #{cue.index} không có nội dung.')
        if cue.end_ms <= cue.start_ms:
            raise ValueError(f'Subtitle #{cue.index} có thời gian kết thúc không hợp lệ.')
        if previous_end is not None:
            if cue.start_ms < previous_end:
                raise ValueError(f'Subtitle #{cue.index} bị chồng timestamp với câu trước.')
            if cue.start_ms - previous_end > max_gap_ms:
                raise ValueError(f'Subtitle #{cue.index} có khoảng lặng quá dài.')
        previous_end = cue.end_ms
    return True
