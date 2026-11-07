"""The Dify runner's moderation settings, read from the same files its DSL is built from (research R3).

`infra/dify/moderation-keywords.txt` and `infra/dify/preset-responses.json` are the single source: the runner's
keyword moderation embeds them, and the backend uses them to recognise a reply that is Dify's preset input refusal and
to filter suggested questions the same way Dify filters answers.
"""

import json
from functools import lru_cache
from pathlib import Path

DIFY_DIR = Path(__file__).resolve().parents[3] / "infra" / "dify"
KEYWORDS_FILE = DIFY_DIR / "moderation-keywords.txt"
PRESETS_FILE = DIFY_DIR / "preset-responses.json"


@lru_cache
def keywords() -> tuple[str, ...]:
    """Non-comment, non-empty lines, lower-cased like Dify compares them."""
    lines = KEYWORDS_FILE.read_text(encoding="utf-8").splitlines()
    return tuple(line.strip().lower() for line in lines if line.strip() and not line.lstrip().startswith("#"))


@lru_cache
def presets() -> dict[str, str]:
    return json.loads(PRESETS_FILE.read_text(encoding="utf-8"))


def contains_blocked_keyword(text: str) -> bool:
    """Same test as Dify's keyword moderation: case-insensitive substring, no diacritic folding."""
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords())


def is_preset_input_block(text: str) -> bool:
    """The runner answered with its preset input refusal, i.e. its own input moderation blocked the message."""
    return text.strip() == presets()["input_blocked"].strip()
