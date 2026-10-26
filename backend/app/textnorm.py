"""Vietnamese text folding shared by the router and the guards.

Students often type without diacritics ("giai ho e bai nay"), so keyword rules match on folded text: lowercase,
no accents, đ -> d, single spaces.
"""

import re
import unicodedata

_SPACES = re.compile(r"\s+")
_WORDS = re.compile(r"[a-z0-9]+")


def fold(text: str) -> str:
    text = unicodedata.normalize("NFD", text.replace("đ", "d").replace("Đ", "D"))
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return _SPACES.sub(" ", text.lower()).strip()


def words(text: str) -> list[str]:
    """Folded word tokens."""
    return _WORDS.findall(fold(text))
