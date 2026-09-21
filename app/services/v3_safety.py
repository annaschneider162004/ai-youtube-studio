from difflib import SequenceMatcher
import re

PATTERNS = [
    r"\bfake\s+(views?|likes?|subscribers?|comments?)\b",
    r"\bbuy\s+(views?|likes?|subscribers?)\b",
    r"\bbypass\b.*\b(captcha|limit|restriction|ban)\b",
    r"\bevade\b.*\b(restriction|ban|detection)\b"
]

def review(title, description="", recent_titles=None):
    issues = []
    text = title + "\n" + description
    for pattern in PATTERNS:
        if re.search(pattern, text, re.I):
            issues.append("Potential fake-engagement/evasion language.")
    for old in recent_titles or []:
        score = SequenceMatcher(None, title.lower(), old.lower()).ratio()
        if score >= 0.88:
            issues.append(f"Title highly similar to existing title ({score:.0%}).")
    if not 3 <= len(title) <= 100:
        issues.append("Title length must be between 3 and 100 characters.")
    return {"ok": not issues, "issues": issues}
