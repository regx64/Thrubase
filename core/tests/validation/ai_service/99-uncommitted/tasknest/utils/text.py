import re

_SLUG = re.compile(r"[^a-z0-9]+")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)


def make_slug(value: str) -> str:
    return _SLUG.sub("-", value.lower()).strip("-")


def normalize_name(value: str) -> str:
    return " ".join(value.split())[:120]


def is_email(value: str) -> bool:
    return bool(_EMAIL.match(value))
