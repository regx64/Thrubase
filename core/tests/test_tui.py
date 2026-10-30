"""T9: one repository climbed to the summit in the terminal."""

from __future__ import annotations

import io
from pathlib import Path

from rich.console import Console

from thrubase.api import Session
from thrubase.tui import Climb


class Answers:
    """Answers every checkpoint by peeking at the server-side trail (tests only)."""

    def __init__(self, session: Session, wrong_for: set[str], skip_for: set[str]) -> None:
        self.s = session
        self.wrong_for = wrong_for
        self.skip_for = skip_for
        self.asked: list[str] = []
        self.pending: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.asked.append(prompt)
        if "[y/N]" in prompt:
            return "n"
        if self.pending:
            return self.pending.pop(0)
        trail = next(iter(self.s._trails.values()))
        for seg in trail.segments:
            for cp in seg.checkpoints:
                st = self._state(trail, seg, cp)
                if st in ("passed", "revealed", "skipped"):
                    continue
                if seg.title in self.skip_for:
                    return "s"
                if cp.options:
                    right = str([o.id for o in cp.options].index(cp.answer) + 1)
                    wrong = str(1 if right != "1" else 2)
                else:
                    right, wrong = str(cp.answer[0][0]), "999999"
                if seg.title in self.wrong_for:
                    self.pending = [wrong]
                    return wrong
                return right
        raise AssertionError("asked after the summit")

    def _state(self, trail, seg, cp) -> str:  # type: ignore[no-untyped-def]
        cur = self.s.dispatch("trail.current", {})
        return str(cur["progress"]["segments"][seg.key]["checkpoints"][cp.id.rsplit(":", 1)[1]]["state"])


def test_climb_to_summit(copy_fixture) -> None:  # type: ignore[no-untyped-def]
    root: Path = copy_fixture("calls_app")
    session = Session(root, lang="en")
    out = io.StringIO()
    console = Console(file=out, width=120, color_system=None)
    answers = Answers(session, wrong_for={"load_config"}, skip_for={"Server.loop"})
    assert Climb(session, console=console, ask=answers).run("full") == 0
    text = out.getvalue()
    assert "Summit reached" in text
    assert "Worth another look" in text
    assert "Unsure · load_config" in text
    assert "Skipped · Server.loop" in text
    assert "Climbing without guides" in text
    assert "Not quite." in text


def test_quit_and_resume_in_korean(copy_fixture) -> None:  # type: ignore[no-untyped-def]
    root: Path = copy_fixture("calls_app")
    session = Session(root, lang="ko")
    out = io.StringIO()
    console = Console(file=out, width=120, color_system=None)
    calls = iter(["s", "q"])
    Climb(session, console=console, ask=lambda p: next(calls)).run("full")
    assert "등반을 멈췄습니다" in out.getvalue()
    out2 = io.StringIO()
    session2 = Session(root, lang="ko")
    answers = Answers(session2, set(), set())
    Climb(session2, console=Console(file=out2, width=120, color_system=None), ask=answers).run("full")
    assert "이어갑니다" in out2.getvalue()
    assert "정상에 도착했습니다" in out2.getvalue()
