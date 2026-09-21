from difflib import SequenceMatcher
import re

BLOCK_PATTERNS = [
    r'\bfake\s+(views?|likes?|subscribers?|comments?)\b',
    r'\bbuy\s+(views?|likes?|subscribers?|comments?)\b',
    r'\bbypass\b.*\b(captcha|limit|restriction|ban|detection)\b',
    r'\bevade\b.*\b(restriction|ban|detection)\b',
]

def review(title, description='', recent_titles=None, duplicate_threshold=0.88):
    issues=[]; warnings=[]
    text = (title or '') + '\n' + (description or '')
    for p in BLOCK_PATTERNS:
        if re.search(p, text, re.I): issues.append('Blocked language: fake engagement or system-evasion.')
    if not 3 <= len(title or '') <= 100: warnings.append('Title should be between 3 and 100 characters.')
    for old in recent_titles or []:
        score = SequenceMatcher(None, (title or '').lower(), old.lower()).ratio()
        if score >= duplicate_threshold and title.strip().lower() != old.strip().lower():
            warnings.append(f'Title is highly similar to an existing title ({score:.0%}).')
    return {'ok': not issues, 'blocked': bool(issues), 'issues': issues, 'warnings': warnings}
