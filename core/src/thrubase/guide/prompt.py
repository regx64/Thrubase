"""Guide prompt templates. Bump ``PROMPT_VERSION`` whenever the wording changes; it is part
of the cache key."""

from __future__ import annotations

from dataclasses import dataclass

PROMPT_VERSION = "1"
MAX_CHARS = 300
LANG_NAMES = {"en": "English", "ko": "Korean (한국어)"}

SYSTEM = (
    "You write a short reading guide for one step of a code walkthrough.\n"
    "Say only what to look at and why it matters. Never state what the code\n"
    "returns, which function is called next, or anything that answers a\n"
    "question about this step. No preamble. 2-3 sentences. Language: {lang}."
)

USER = (
    "Step {order} of {total}. Previous step: {prev_title}. Next step: {next_title}.\n"
    "File: {file}, lines {start}-{end}.\n"
    "{code}"
)


@dataclass
class GuideRequest:
    order: int
    total: int
    prev_title: str
    next_title: str
    file: str
    start: int
    end: int
    code: str
    lang: str
    #: strings the guide must not contain (the checkpoint answers of this segment)
    forbidden: tuple[str, ...] = ()

    def system(self) -> str:
        return SYSTEM.format(lang=LANG_NAMES.get(self.lang, "English"))

    def user(self) -> str:
        return USER.format(order=self.order, total=self.total, prev_title=self.prev_title or "none",
                           next_title=self.next_title or "none", file=self.file, start=self.start,
                           end=self.end, code=self.code)


def clean(text: str) -> str:
    text = " ".join(text.strip().split())
    if len(text) > MAX_CHARS:
        cut = text[:MAX_CHARS]
        stop = max(cut.rfind(". "), cut.rfind("다. "), cut.rfind("? "))
        text = cut[: stop + 1] if stop > 80 else cut.rstrip() + "…"
    return text


def names_answer(text: str, forbidden: tuple[str, ...]) -> bool:
    low = text.lower()
    for f in forbidden:
        f = f.strip("`").lower()
        if not f:
            continue
        short = f.rsplit(".", 1)[-1]
        if f in low or (len(short) >= 4 and short in low):
            return True
    return False
