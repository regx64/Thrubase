"""T7: guides from both providers against a mock server, caching, failures, answer checks."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from thrubase.api import LLM_FAILED, ApiError, Session
from thrubase.guide.prompt import GuideRequest, clean, names_answer
from thrubase.guide.providers import ProviderError, make_provider
from thrubase.guide.service import GuideService
from thrubase.store import Config, Store

FIX = Path(__file__).parent / "fixtures"


def req(**kw) -> GuideRequest:  # type: ignore[no-untyped-def]
    base = dict(order=2, total=12, prev_title="main", next_title="Router.find", file="app/router.py", start=1,
                end=3, code="def f():\n    return g()\n", lang="ko", forbidden=("Router.find",))
    base.update(kw)
    return GuideRequest(**base)  # type: ignore[arg-type]


class Recorder:
    def __init__(self, replies: list[httpx.Response]) -> None:
        self.replies = replies
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.replies.pop(0)


def anthropic_reply(text: str) -> httpx.Response:
    return httpx.Response(200, json={"content": [{"type": "text", "text": text}]})


def openai_reply(text: str) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def test_anthropic_request_shape_and_cache(store: Store) -> None:
    rec = Recorder([anthropic_reply("Look at how the request is split. It decides the route.")])
    cfg = Config(llm_provider="anthropic", api_key="sk-test", llm_model="claude-test")
    svc = GuideService(store, cfg, transport=httpx.MockTransport(rec))
    guide, cached = svc.guide(req())
    assert guide and not cached
    r = rec.requests[0]
    assert r.url == "https://api.anthropic.com/v1/messages"
    assert r.headers["x-api-key"] == "sk-test" and r.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(r.content)
    assert body["model"] == "claude-test"
    assert "Language: Korean" in body["system"]
    assert "Step 2 of 12. Previous step: main. Next step: Router.find." in body["messages"][0]["content"]
    # Second call: served from cache, no network.
    svc2 = GuideService(store, cfg, transport=httpx.MockTransport(lambda r: pytest.fail("network used")))
    assert svc2.guide(req()) == (guide, True)
    # The key is never stored.
    assert "sk-test" not in "".join(p.read_text() for p in store.home.rglob("*.json"))


def test_openai_compatible_and_ollama(store: Store) -> None:
    rec = Recorder([openai_reply("Notice the loop over lines.")])
    cfg = Config(llm_provider="openai-compatible", llm_endpoint="http://localhost:11434/v1", llm_model="llama3")
    svc = GuideService(store, cfg, transport=httpx.MockTransport(rec))
    assert svc.guide(req())[0] == "Notice the loop over lines."
    r = rec.requests[0]
    assert str(r.url) == "http://localhost:11434/v1/chat/completions"
    assert "authorization" not in r.headers
    body = json.loads(r.content)
    assert body["messages"][0]["role"] == "system"


def test_retry_once_then_fail(store: Store) -> None:
    rec = Recorder([httpx.Response(500), httpx.Response(503)])
    p = make_provider("anthropic", "k", transport=httpx.MockTransport(rec))
    assert p is not None
    with pytest.raises(ProviderError):
        p.complete("s", "u")
    assert len(rec.requests) == 2


def test_timeouts_are_errors(store: Store) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    p = make_provider("openai-compatible", "k", transport=httpx.MockTransport(boom))
    assert p is not None
    with pytest.raises(ProviderError):
        p.complete("s", "u")


def test_guide_naming_the_answer_is_discarded(store: Store) -> None:
    rec = Recorder([anthropic_reply("It calls Router.find next."), anthropic_reply("Then find() runs.")])
    svc = GuideService(store, Config(llm_provider="anthropic", api_key="k"), transport=httpx.MockTransport(rec))
    assert svc.guide(req()) == (None, False)
    assert len(rec.requests) == 2
    rec2 = Recorder([anthropic_reply("It calls Router.find next."), anthropic_reply("Watch the dictionary lookup.")])
    svc2 = GuideService(store, Config(llm_provider="anthropic", api_key="k2"), transport=httpx.MockTransport(rec2))
    assert svc2.guide(req(code="other"))[0] == "Watch the dictionary lookup."


def test_no_provider_means_no_guide(store: Store) -> None:
    svc = GuideService(store, Config())
    assert not svc.enabled
    assert svc.guide(req()) == (None, False)
    assert make_provider("anthropic", "") is None


def test_clean_and_names_answer() -> None:
    long = "Sentence one is here. " * 30
    assert len(clean(long)) <= 300
    assert names_answer("we call find soon", ("Router.find",))
    assert not names_answer("we look at the loop", ("Router.find",))


def test_api_without_key_and_with_failure(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    s = Session(FIX / "calls_app", store=store)
    t = s.dispatch("trail.build", {"kind": "full"})
    assert s.dispatch("segment.guide", {"trailId": t["id"], "order": 1}) == {"guide": None, "cached": False}
    s.guides = GuideService(store, Config(llm_provider="anthropic", api_key="k"),
                            transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    with pytest.raises(ApiError) as exc:
        s.dispatch("segment.guide", {"trailId": t["id"], "order": 1})
    assert exc.value.code == LLM_FAILED
