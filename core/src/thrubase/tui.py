"""Terminal climb (rich): segment code, questions, hints, skip, summit review list."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from .api import LLM_FAILED, ApiError, Session
from .i18n import t

InputFn = Callable[[str], str]


class Quit(Exception):
    pass


class Climb:
    def __init__(self, session: Session, console: Console | None = None, ask: InputFn | None = None) -> None:
        self.s = session
        self.console = console or Console(highlight=False)
        self.ask = ask or (lambda prompt: self.console.input(prompt))
        self.lang = session.lang

    def _t(self, key: str, **params: Any) -> str:
        return t(self.lang, key, **params)

    def run(self, kind: str = "full", since: str | None = None, restart: bool = False) -> int:
        trail = self.s.dispatch("trail.build", {"kind": kind, "since": since})
        if restart:
            trail["progress"] = self.s.dispatch("progress.reset", {"trailId": trail["id"]})
        progress = trail["progress"]
        segments = trail["segments"]
        main = [s for s in segments if not s["detour"]]
        kind_label = self._t("term.full_climb" if kind == "full" else "term.diff_climb")
        root_name = Path(str(self.s.root)).name
        self.console.print(Text(self._t("climb.header", kind=kind_label, name=root_name, count=len(main)),
                                style="bold"))
        started = [s for s in segments if self._status(progress, s) != "todo"]
        if started and progress.get("current"):
            self.console.print(self._t("climb.resume", order=progress["current"]))
        try:
            for seg in segments:
                if self._status(progress, seg) != "todo":
                    continue
                if seg["detour"]:
                    answer = self.ask(f"{self._t('climb.detour')} · {seg['title']} [y/N] ").strip().lower()
                    if answer not in ("y", "yes", "예", "ㅛ"):
                        continue
                progress = self._segment(trail, seg, progress, len(main))
        except Quit:
            self.console.print(self._t("climb.paused"))
            return 0
        self._summit(trail, progress)
        return 0

    @staticmethod
    def _status(progress: dict[str, Any], seg: dict[str, Any]) -> str:
        key = "|".join(sorted(seg["nodes"]))
        return str(progress["segments"].get(key, {}).get("status", "todo"))

    def _segment(self, trail: dict[str, Any], seg: dict[str, Any], progress: dict[str, Any],
                 total: int) -> dict[str, Any]:
        self.console.rule()
        number = self._t("climb.detour") if seg["detour"] else self._t("climb.segment", order=seg["order"],
                                                                         total=total)
        changed = f" · {self._t('climb.changed')}" if seg.get("changed") else ""
        self.console.print(Text(f"{number} · {seg['title']}{changed}", style="bold"))
        self.console.print(Text(f"{seg['file']}:{seg['start_line']}–{seg['end_line']}", style="dim"))
        try:
            guide = self.s.dispatch("segment.guide", {"trailId": trail["id"], "order": seg["order"]})["guide"]
        except ApiError as exc:
            if exc.code != LLM_FAILED:
                raise
            guide = None
        self.console.print(guide if guide else Text(self._t("climb.guide.none"), style="dim"))
        code = self.s.dispatch("segment.code", {"trailId": trail["id"], "order": seg["order"], "context": 3})
        lines = code["lines"]
        shown = lines if len(lines) <= 80 else [*lines[:80], "…"]
        self.console.print(Syntax("\n".join(shown), "python", line_numbers=True, start_line=code["startLine"],
                                  highlight_lines=set(range(code["highlight"][0], code["highlight"][1] + 1)),
                                  word_wrap=False, theme="ansi_dark"))
        for cp in seg["checkpoints"]:
            progress = self._checkpoint(cp, progress)
        return progress

    def _checkpoint(self, cp: dict[str, Any], progress: dict[str, Any]) -> dict[str, Any]:
        label = self._t(f"cp.type.{cp['type']}")
        self.console.print(Panel(Text(cp["prompt"]), title=label, title_align="left", expand=False))
        options = cp.get("options") or []
        for i, o in enumerate(options, start=1):
            self.console.print(f"  {i}. {o['label']}")
        help_text = self._t("climb.options", n=len(options)) if options else self._t("climb.locate")
        while True:
            raw = self.ask(f"{help_text} › ").strip().lower()
            if raw == "q":
                raise Quit()
            if raw == "s":
                result: dict[str, Any] = self.s.dispatch("checkpoint.skip", {"checkpointId": cp["id"]})
                self.console.print(Text(self._t("climb.skipped"), style="dim"))
                return result
            if options:
                if not raw.isdigit() or not 1 <= int(raw) <= len(options):
                    self.console.print(self._t("climb.invalid"))
                    continue
                answer: Any = options[int(raw) - 1]["id"]
            else:
                if not raw.isdigit():
                    self.console.print(self._t("climb.invalid"))
                    continue
                answer = int(raw)
            res = self.s.dispatch("checkpoint.answer", {"checkpointId": cp["id"], "answer": answer})
            if res["result"] == "correct":
                self.console.print(Text(f"✓ {self._t('climb.correct')}", style="green"))
                self.console.print(Text(res.get("explanation", ""), style="dim"))
                return dict(res["progress"])
            if res["result"] == "hint":
                self.console.print(Text(f"{self._t('climb.hint')} {res.get('hint', '')}", style="yellow"))
                continue
            shown = self._answer_label(cp, res.get("answer"))
            self.console.print(Text(f"⚠ {self._t('climb.revealed', answer=shown)}", style="yellow"))
            self.console.print(res.get("explanation", ""))
            return dict(res["progress"])

    @staticmethod
    def _answer_label(cp: dict[str, Any], answer: Any) -> str:
        for o in cp.get("options") or []:
            if o["id"] == answer:
                return str(o["label"])
        if isinstance(answer, list) and answer:
            return ", ".join(f"{a}" if a == b else f"{a}–{b}" for a, b in answer)
        return str(answer)

    def _summit(self, trail: dict[str, Any], progress: dict[str, Any]) -> None:
        self.console.rule()
        self.console.print(Text(f"▲ {self._t('climb.summit')}", style="bold"))
        review = [s for s in trail["segments"] if self._status(progress, s) in ("weak", "skipped")]
        if not review:
            self.console.print(self._t("climb.review.none"))
            return
        self.console.print(Text(self._t("climb.review"), style="bold"))
        for s in review:
            status = self._status(progress, s)
            icon = "⚠" if status == "weak" else "↷"
            self.console.print(f"  {icon} {self._t('status.' + status)} · {s['title']} "
                               f"[dim]{s['file']}:{s['start_line']}[/dim]")
