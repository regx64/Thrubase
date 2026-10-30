"""T8: en and ko have the same keys; glossary terms are exact."""

import json
import re
from importlib import resources

from thrubase.i18n import messages, render, resolve_lang


def load(lang: str) -> dict[str, str]:
    return json.loads(resources.files("thrubase.i18n").joinpath(f"{lang}.json").read_text(encoding="utf-8"))


def test_same_keys() -> None:
    en, ko = load("en"), load("ko")
    assert set(en) == set(ko), set(en) ^ set(ko)


def test_same_placeholders() -> None:
    en, ko = load("en"), load("ko")
    for key in en:
        assert set(re.findall(r"{(\w+)}", en[key])) == set(re.findall(r"{(\w+)}", ko[key])), key


def test_glossary() -> None:
    ko = messages("ko")
    en = messages("en")
    glossary = {
        "term.terrain_map": ("Terrain map", "지형도"), "term.trail": ("Trail", "등산로"),
        "term.segment": ("Segment", "구간"), "term.checkpoint": ("Checkpoint", "체크포인트"),
        "term.entry": ("Entry", "진입점"), "term.summit": ("Summit", "정상"), "term.detour": ("Detour", "샛길"),
        "term.isolated": ("Isolated zone", "고립 지대"), "status.passed": ("Passed", "통과"),
        "status.weak": ("Unsure", "미확보"), "status.skipped": ("Skipped", "건너뜀"),
    }
    for key, (e, k) in glossary.items():
        assert en[key] == e and ko[key] == k


def test_no_exclamation_marks() -> None:
    for lang in ("en", "ko"):
        for key, value in load(lang).items():
            assert "!" not in value, (lang, key)


def test_render_and_lang() -> None:
    assert render("ko", "cp.flow", {"a": "main"}) == "`main`는 이 중 무엇을 가장 먼저 호출하나요?"
    assert render("xx", "cp.flow", {"a": "main"}) == "Which of these does `main` call first?"
    assert render("en", "missing.key") == "missing.key"
    assert resolve_lang("ko") == "ko"
    assert resolve_lang("auto") in ("en", "ko")
