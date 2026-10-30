"""Guide generation with response checks and caching."""

from __future__ import annotations

import httpx

from ..store import Config, Store
from .cache import GuideCache, cache_key
from .prompt import GuideRequest, clean, names_answer
from .providers import Provider, ProviderError, make_provider


class GuideService:
    def __init__(self, store: Store, config: Config, transport: httpx.BaseTransport | None = None) -> None:
        self.cache = GuideCache(store)
        self.provider: Provider | None = make_provider(
            config.llm_provider, config.api_key, config.llm_model, config.llm_endpoint, transport)

    @property
    def enabled(self) -> bool:
        return self.provider is not None

    def guide(self, req: GuideRequest) -> tuple[str | None, bool]:
        """Returns ``(guide, cached)``. ``None`` when no provider is set, the call failed, or
        both attempts named a checkpoint answer. Raises ``ProviderError`` only for failures
        so the caller can report -32004 while continuing without a guide."""
        if self.provider is None:
            return None, False
        key = cache_key(f"{req.file}:{req.start}-{req.end}\n{req.code}\n{req.prev_title}|{req.next_title}",
                        self.provider.model, req.lang)
        hit = self.cache.get(key)
        if hit is not None:
            return hit, True
        for _ in range(2):
            text = clean(self.provider.complete(req.system(), req.user()))
            if text and not names_answer(text, req.forbidden):
                self.cache.put(key, text)
                return text, False
        return None, False


__all__ = ["GuideService", "ProviderError"]
