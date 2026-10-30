"""Guide cache keyed by ``sha256(segment code + model + lang + prompt version)``."""

from __future__ import annotations

import hashlib

from ..store import Store
from .prompt import PROMPT_VERSION


def cache_key(code: str, model: str, lang: str) -> str:
    return hashlib.sha256(f"{code}\0{model}\0{lang}\0{PROMPT_VERSION}".encode()).hexdigest()


class GuideCache:
    def __init__(self, store: Store) -> None:
        self.store = store

    def get(self, key: str) -> str | None:
        data = self.store.read_json(self.store.guide_path(key))
        if isinstance(data, dict) and isinstance(data.get("guide"), str):
            return str(data["guide"])
        return None

    def put(self, key: str, guide: str) -> None:
        self.store.write_json(self.store.guide_path(key), {"guide": guide})
