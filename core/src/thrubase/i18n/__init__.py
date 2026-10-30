"""CLI, question and guide strings in English and Korean.

Terms follow the design system glossary exactly (Terrain map · 지형도, Trail · 등산로,
Segment · 구간, Checkpoint · 체크포인트, Entry · 진입점, Summit · 정상, Detour · 샛길,
Isolated zone · 고립 지대, Passed / Unsure / Skipped · 통과 / 미확보 / 건너뜀).
"""

from __future__ import annotations

import json
import locale
import os
from functools import cache
from importlib import resources
from typing import Any

LANGS = ("en", "ko")


@cache
def messages(lang: str) -> dict[str, str]:
    lang = lang if lang in LANGS else "en"
    text = resources.files(__package__).joinpath(f"{lang}.json").read_text(encoding="utf-8")
    data: dict[str, str] = json.loads(text)
    return data


def resolve_lang(lang: str | None) -> str:
    """``auto`` (or nothing) follows the environment's locale; anything unknown is English."""
    if lang in LANGS:
        return str(lang)
    for var in ("THRUBASE_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(var, "")
        if value and value != "auto":
            return "ko" if value.lower().startswith("ko") else "en"
    try:
        loc = locale.getlocale()[0] or ""
    except ValueError:  # pragma: no cover
        loc = ""
    return "ko" if loc.lower().startswith("ko") else "en"


def render(lang: str, key: str, params: dict[str, Any] | None = None, /) -> str:
    template = messages(lang).get(key) or messages("en").get(key) or key
    try:
        return template.format(**(params or {}))
    except (KeyError, IndexError):
        return template


def t(lang: str, key: str, /, **params: Any) -> str:
    return render(lang, key, params)
