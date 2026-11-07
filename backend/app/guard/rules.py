"""Personal data redaction: the one content rule that stays in the platform (FR-015).

Messages are redacted before anything leaves the platform (Dify, tracing, guard_events excerpts); every content
guardrail itself runs in Dify (triage, keyword moderation, review; see app/runtime/dify_turn.py).
"""

import re
import unicodedata


def fold_chars(text: str) -> str:
    """Folds character by character so match positions map back onto the NFC original (unlike `fold`)."""
    out = []
    for char in text:
        base = unicodedata.normalize("NFD", char.replace("đ", "d").replace("Đ", "D"))
        kept = "".join(c for c in base if unicodedata.category(c) != "Mn") or char
        out.append(kept[0].lower())
    return "".join(out)


PHONE = re.compile(r"(?<![\d.])(?:\+84|0)(?:[\s.-]?\d){9,10}(?![\d])")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
ID_NUMBER = re.compile(r"(?<!\d)\d{12}(?!\d)")
# Positions found on the folded text and replaced in the original.
PASSWORD = re.compile(r"mat khau(?: zalo| facebook| fb| email| cua (?:minh|em|toi))?\s*(?:la|:)\s*([^\s,;]+)")
ADDRESS = re.compile(r"\bso \d+[a-z]?(?:/\d+)? (?:ngo|ngach|hem|kiet|duong|pho)\b[^,.;\n]{0,40}")

PII_NAMES = {
    "email": "email",
    "phone": "số điện thoại",
    "id_number": "số giấy tờ",
    "password": "mật khẩu",
    "address": "địa chỉ",
}


def redact(text: str) -> tuple[str, list[str]]:
    """Replaces phone numbers, emails, ID numbers, passwords and street addresses. Returns the text and what was
    found (as kinds, never the values)."""
    text = unicodedata.normalize("NFC", text)
    found: list[str] = []
    for pattern, label, kind in (
        (EMAIL, "[email đã ẩn]", "email"),
        (PHONE, "[số điện thoại đã ẩn]", "phone"),
        (ID_NUMBER, "[số giấy tờ đã ẩn]", "id_number"),
    ):
        text, count = pattern.subn(label, text)
        if count:
            found.append(kind)
    for pattern, label, kind, group in (
        (PASSWORD, "[mật khẩu đã ẩn]", "password", 1),
        (ADDRESS, "[địa chỉ đã ẩn]", "address", 0),
    ):
        spans = [match.span(group) for match in pattern.finditer(fold_chars(text))]
        for start, end in reversed(spans):
            text = text[:start] + label + text[end:]
        if spans:
            found.append(kind)
    return text, found
