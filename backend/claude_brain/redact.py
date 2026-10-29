"""Secret redaction applied to everything the API returns."""
import re

_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}"),
    re.compile(r"(?i)\b(password|passwd|pwd|secret|api[_-]?key|token|credential\w*)\b(\s*[:=]\s*)(\S+)"),
]


def redact(text):
    if not text:
        return text
    for i, p in enumerate(_PATTERNS):
        if i == len(_PATTERNS) - 1:
            text = p.sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", text)
        else:
            text = p.sub("[REDACTED]", text)
    return text
