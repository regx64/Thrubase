"""The one set of methods every client uses (terminal, VS Code over JSON-RPC, web over HTTP).

Method names, parameters and results are identical across transports. Answers never leave
this module: clients get checkpoints without answers, and grading always happens here.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from . import SCHEMA_VERSION, __version__
from .engine import checkpoint as cpmod
from .engine import trail as trailmod
from .engine.diff import BadRevision, GitError, GitMissing, NotARepository, count_changed_functions, graph_diff
from .engine.pipeline import Analysis, CancelToken, Engine, NoSupportedFiles
from .guide.prompt import GuideRequest
from .guide.providers import ProviderError
from .guide.service import GuideService
from .i18n import render, resolve_lang
from .model import (
    Checkpoint,
    CheckpointState,
    Progress,
    SegmentProgress,
    Trail,
    from_json,
    to_json,
)
from .store import Config, Store

# JSON-RPC error codes (also used as HTTP error bodies)
NO_SUPPORTED_LANGUAGE = -32001
NOT_A_GIT_REPOSITORY = -32002
NO_CHANGES = -32003
LLM_FAILED = -32004
SCHEMA_MISMATCH = -32005
INVALID_PARAMS = -32602
METHOD_NOT_FOUND = -32601
REQUEST_CANCELLED = -32800
INTERNAL_ERROR = -32603

CODE_CONTEXT = 3


_FINISHED: dict[str, Literal["passed", "revealed", "skipped"]] = {
    "passed": "passed", "weak": "revealed", "skipped": "skipped"}


class ApiError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            d["data"] = self.data
        return d


Notify = Callable[[str, dict[str, Any]], None]


def _segment_status(states: dict[str, CheckpointState]) -> str:
    values = [s.state for s in states.values()]
    if not values:
        return "todo"
    if "revealed" in values:
        return "weak"
    if "skipped" in values:
        return "skipped"
    if all(v == "passed" for v in values):
        return "passed"
    return "todo"


class Session:
    """State for one repository root. Thread-safe enough for one client issuing requests
    while a long ``map.build`` runs: the engine is guarded by a lock."""

    def __init__(self, root: Path | str | None = None, *, store: Store | None = None,
                 config_overrides: dict[str, Any] | None = None, lang: str | None = None,
                 notify: Notify | None = None) -> None:
        self.store = store or Store()
        self._overrides = config_overrides or {}
        self.config: Config = self.store.load_config(self._overrides)
        self.lang = resolve_lang(lang or self.config.lang)
        self.root: Path | None = Path(root).resolve() if root else None
        self.notify: Notify = notify or (lambda method, params: None)
        self._engine: Engine | None = None
        self._lock = threading.RLock()
        self._trails: dict[str, Trail] = {}
        self._contexts: dict[str, cpmod.Context] = {}
        self.guides = GuideService(self.store, self.config)

    # ------------------------------------------------------------------ plumbing
    @property
    def engine(self) -> Engine:
        if self.root is None:
            raise ApiError(INVALID_PARAMS, "initialize with a root first")
        if self._engine is None or self._engine.root != self.root:
            self._engine = Engine(self.root, store=self.store, config=self.config)
        return self._engine

    def dispatch(self, method: str, params: dict[str, Any] | None, cancel: CancelToken | None = None) -> Any:
        handler = METHODS.get(method)
        if handler is None:
            raise ApiError(METHOD_NOT_FOUND, f"unknown method {method}")
        params = params or {}
        if not isinstance(params, dict):
            raise ApiError(INVALID_PARAMS, "params must be an object")
        try:
            return handler(self, params, cancel or CancelToken())
        except ApiError:
            raise
        except NoSupportedFiles as exc:
            raise ApiError(NO_SUPPORTED_LANGUAGE, render(self.lang, "cli.error.unsupported")) from exc
        except NotARepository as exc:
            raise ApiError(NOT_A_GIT_REPOSITORY, render(self.lang, "cli.error.not_git")) from exc
        except GitMissing as exc:
            raise ApiError(NOT_A_GIT_REPOSITORY, render(self.lang, "cli.error.no_git")) from exc
        except BadRevision as exc:
            raise ApiError(INVALID_PARAMS, render(self.lang, "cli.error.bad_ref", {"ref": str(exc)})) from exc
        except trailmod.NoChanges as exc:
            raise ApiError(NO_CHANGES, render(self.lang, "cli.error.no_changes")) from exc
        except GitError as exc:
            raise ApiError(INTERNAL_ERROR, str(exc)) from exc
        except (KeyError, ValueError) as exc:
            raise ApiError(INVALID_PARAMS, f"invalid params: {exc}") from exc

    def _analysis(self, cancel: CancelToken | None = None, no_cache: bool = False) -> Analysis:
        def progress(stage: str, done: int, total: int) -> None:
            self.notify("$/progress", {"stage": stage, "done": done, "total": total})

        with self._lock:
            return self.engine.analyze(no_cache=no_cache, on_progress=progress, cancel=cancel)

    def _public(self, value: Any) -> dict[str, Any]:
        out: dict[str, Any] = to_json(value)
        return out

    # ------------------------------------------------------------------ trails & progress
    def _save_trail(self, trail: Trail) -> None:
        assert self.root is not None
        self.store.write_json(self.store.trail_path(self.root, trail.id), to_json(trail))
        self._trails[trail.id] = trail

        def set_current(cur: Any) -> dict[str, Any]:
            current: dict[str, Any] = cur if isinstance(cur, dict) else {}
            current[trail.kind] = trail.id
            current["last"] = trail.id
            return current

        self.store.update_json(self.store.current_path(self.root), set_current)

    def _load_trail(self, trail_id: str) -> Trail:
        if trail_id in self._trails:
            return self._trails[trail_id]
        assert self.root is not None
        data = self.store.read_json(self.store.trail_path(self.root, trail_id))
        if not isinstance(data, dict):
            raise ApiError(INVALID_PARAMS, f"unknown trail {trail_id}")
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ApiError(SCHEMA_MISMATCH, "trail was built by an incompatible version; build it again")
        trail = from_json(Trail, data)
        self._trails[trail_id] = trail
        return trail

    def _progress_path(self, kind: str) -> Path:
        assert self.root is not None
        return self.store.progress_path(self.root, kind)

    def _read_progress(self, trail: Trail) -> Progress:
        data = self.store.read_json(self._progress_path(trail.kind))
        prog = from_json(Progress, data) if isinstance(data, dict) else Progress(trail_id=trail.id, kind=trail.kind)
        return self._fit(prog, trail)

    @staticmethod
    def _fit(prog: Progress, trail: Trail) -> Progress:
        """Keep the status of segments whose node ids survive a rebuilt trail."""
        keys = {s.key for s in trail.segments}
        segments = {k: v for k, v in prog.segments.items() if k in keys}
        for s in trail.segments:
            sp = segments.get(s.key) or SegmentProgress(key=s.key)
            slots = {c.id.rsplit(":", 1)[1] for c in s.checkpoints}
            sp.checkpoints = {k: v for k, v in sp.checkpoints.items() if k in slots}
            for slot in slots:
                sp.checkpoints.setdefault(slot, CheckpointState())
            if sp.status != "todo":
                # A segment keeps a finished status even if a question changed with the code.
                for st in sp.checkpoints.values():
                    if st.state == "idle":
                        st.state = _FINISHED[sp.status]
            sp.status = _segment_status(sp.checkpoints)  # type: ignore[assignment]
            segments[s.key] = sp
        prog = Progress(trail_id=trail.id, kind=trail.kind, segments=segments, current=None, updated=prog.updated)
        prog.current = next((s.order for s in trail.segments
                             if not s.detour and segments[s.key].status == "todo"), None)
        return prog

    def _write_progress(self, trail: Trail, fn: Callable[[Progress], None]) -> Progress:
        result: dict[str, Progress] = {}

        def update(cur: Any) -> Any:
            prog = from_json(Progress, cur) if isinstance(cur, dict) else Progress(trail_id=trail.id, kind=trail.kind)
            prog = self._fit(prog, trail)
            fn(prog)
            prog = self._fit(prog, trail)
            prog.updated = time.time()
            result["p"] = prog
            return to_json(prog)

        self.store.update_json(self._progress_path(trail.kind), update)
        return result["p"]

    def _context(self, trail: Trail, analysis: Analysis) -> cpmod.Context:
        return cpmod.Context(map=analysis.map, files={f.path: f for f in analysis.files}, edges=analysis.edges)

    def _render(self, cp: Checkpoint, part: str) -> str:
        value = cp.text.get(part)
        if not value:
            return str(getattr(cp, part))
        if part == "explanation":
            return " ".join(render(self.lang, k, p) for k, p in value)
        return render(self.lang, value[0], value[1])

    def _public_trail(self, trail: Trail) -> dict[str, Any]:
        d = trail.public()
        for seg, seg_d in zip(trail.segments, d["segments"], strict=True):
            for cp, cp_d in zip(seg.checkpoints, seg_d["checkpoints"], strict=True):
                cp_d["prompt"] = self._render(cp, "prompt")
        if trail.diff is not None:
            d["diff"] = to_json(trail.diff)
        return d

    # ------------------------------------------------------------------ methods
    def initialize(self, p: dict[str, Any], cancel: CancelToken) -> dict[str, Any]:
        if p.get("root"):
            self.root = Path(str(p["root"])).resolve()
            self._engine = None
        if p.get("lang"):
            self.lang = resolve_lang(str(p["lang"]))
        if "schemaVersion" in p and int(p["schemaVersion"]) != SCHEMA_VERSION:
            raise ApiError(SCHEMA_MISMATCH, f"client schema {p['schemaVersion']} != server schema {SCHEMA_VERSION}")
        if p.get("apiKey"):
            # VS Code passes the key from SecretStorage through the environment of the child
            # process; this is only for clients that cannot set an environment.
            self.config.api_key = str(p["apiKey"])
            self.guides = GuideService(self.store, self.config)
        from .adapters.base import default_registry

        return {
            "serverVersion": __version__,
            "schemaVersion": SCHEMA_VERSION,
            "languages": default_registry().names,
            "lang": self.lang,
            "root": self.root.as_posix() if self.root else None,
            "guides": self.guides.enabled,
            "suggestThreshold": self.config.suggest_threshold,
        }

    def map_build(self, p: dict[str, Any], cancel: CancelToken) -> dict[str, Any]:
        result: dict[str, Any] = to_json(self._analysis(cancel, no_cache=bool(p.get("noCache"))).map)
        return result

    def trail_build(self, p: dict[str, Any], cancel: CancelToken) -> dict[str, Any]:
        kind = p.get("kind", "full")
        if kind not in ("full", "diff"):
            raise ApiError(INVALID_PARAMS, "kind must be full or diff")
        since = p.get("since") or None
        analysis = self._analysis(cancel)
        cancel.check()
        files = {f.path: f for f in analysis.files}
        ctx = self._context_for(analysis)
        if kind == "full":
            segments = trailmod.full_trail(analysis.map, analysis.graph, files,  # type: ignore[arg-type]
                                           summits=self.config.summits, max_segments=self.config.max_segments)
            tid = trailmod.trail_id("full", analysis.map.repo.snapshot)
            diff = None
        else:
            res = graph_diff(self.engine, analysis, since)
            diff = res.diff
            segments = trailmod.diff_trail(analysis.map, analysis.graph, files, diff,  # type: ignore[arg-type]
                                           max_segments=self.config.max_segments)
            ctx = cpmod.Context(map=analysis.map, files=files, edges=analysis.edges, diff=diff,
                                base_callers=res.base_callers)
            key = "|".join([diff.base, *diff.touched, *(f"{e.src}>{e.dst}" for e in diff.removed_edges)])
            tid = trailmod.trail_id("diff", analysis.map.repo.snapshot, key)
        cpmod.generate(ctx, segments, tid)
        trail = Trail(id=tid, kind=kind, snapshot=analysis.map.repo.snapshot, segments=segments,
                      path=[n for s in segments for n in s.nodes], since=since, diff=diff)
        self._save_trail(trail)
        prog = self._write_progress(trail, lambda pr: None)
        out = self._public_trail(trail)
        out["progress"] = to_json(prog)
        return out

    def _context_for(self, analysis: Analysis) -> cpmod.Context:
        return cpmod.Context(map=analysis.map, files={f.path: f for f in analysis.files}, edges=analysis.edges)

    def trail_current(self, p: dict[str, Any], cancel: CancelToken) -> dict[str, Any] | None:
        if self.root is None:
            raise ApiError(INVALID_PARAMS, "initialize with a root first")
        cur = self.store.read_json(self.store.current_path(self.root))
        if not isinstance(cur, dict):
            return None
        tid = cur.get(p["kind"]) if p.get("kind") else cur.get("last")
        if not tid:
            return None
        try:
            trail = self._load_trail(str(tid))
        except ApiError:
            return None
        prog = self._read_progress(trail)
        return {"trail": self._public_trail(trail), "progress": to_json(prog)}

    def _segment_code(self, trail: Trail, order: int) -> tuple[str, int, int, list[str]]:
        seg = trail.segment(order)
        lines = self._read_lines(seg.file)
        return seg.file, seg.start_line, seg.end_line, lines

    def _read_lines(self, rel: str) -> list[str]:
        assert self.root is not None
        if "\\" in rel or rel.startswith("/") or ":" in rel.split("/")[0]:
            raise ApiError(INVALID_PARAMS, "path outside the repository")
        path = (self.root / rel).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ApiError(INVALID_PARAMS, "path outside the repository") from exc
        if not path.is_file():
            raise ApiError(INVALID_PARAMS, f"no such file {rel}")
        data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        return data.decode("utf-8", "replace").split("\n")

    def segment_guide(self, p: dict[str, Any], cancel: CancelToken) -> dict[str, Any]:
        trail = self._load_trail(str(p["trailId"]))
        order = int(p["order"])
        if not self.guides.enabled:
            return {"guide": None, "cached": False}
        seg = trail.segment(order)
        file, start, end, lines = self._segment_code(trail, order)
        code = "\n".join(lines[start - 1 : end])
        idx = [s.order for s in trail.segments]
        i = idx.index(order)
        prev_title = trail.segments[i - 1].title if i > 0 else ""
        next_title = trail.segments[i + 1].title if i + 1 < len(trail.segments) else ""
        forbidden: list[str] = []
        for cp in seg.checkpoints:
            for o in cp.options:
                if o.id == cp.answer:
                    forbidden.append(o.label)
            if cp.type == "locate":
                b = cp.text.get("prompt", ["", {}])[1].get("b")
                if b:
                    forbidden.append(b)
        req = GuideRequest(order=order, total=len(trail.segments), prev_title=prev_title, next_title=next_title,
                           file=file, start=start, end=end, code=code, lang=self.lang, forbidden=tuple(forbidden))
        try:
            guide, cached = self.guides.guide(req)
        except ProviderError as exc:
            raise ApiError(LLM_FAILED, f"guide unavailable: {exc}") from exc
        return {"guide": guide, "cached": cached}

    def segment_code(self, p: dict[str, Any], cancel: CancelToken) -> dict[str, Any]:
        context = int(p.get("context", CODE_CONTEXT))
        context = max(0, min(context, 50))
        if p.get("file"):
            file = str(p["file"])
            lines = self._read_lines(file)
            start = int(p.get("startLine", 1))
            end = int(p.get("endLine", start))
        else:
            trail = self._load_trail(str(p["trailId"]))
            file, start, end, lines = self._segment_code(trail, int(p["order"]))
        first = max(1, start - context)
        last = min(len(lines), end + context)
        return {"file": file, "startLine": first, "lines": lines[first - 1 : last],
                "highlight": [start, end]}

    def checkpoint_answer(self, p: dict[str, Any], cancel: CancelToken) -> dict[str, Any]:
        cp_id = str(p["checkpointId"])
        trail = self._load_trail(cp_id.split(":", 1)[0])
        seg, cp = trail.checkpoint(cp_id)
        slot = cp_id.rsplit(":", 1)[1]
        answer = p.get("answer")
        outcome: dict[str, Any] = {}

        def apply(prog: Progress) -> None:
            st = prog.segments[seg.key].checkpoints[slot]
            if st.state in ("passed", "revealed", "skipped"):
                outcome["result"] = {"passed": "correct", "revealed": "revealed", "skipped": "revealed"}[st.state]
                return
            st.attempts += 1
            if cpmod.is_correct(cp, answer):
                st.state = "passed"
                outcome["result"] = "correct"
            elif st.attempts == 1:
                st.state = "hint"
                outcome["result"] = "hint"
            else:
                st.state = "revealed"
                outcome["result"] = "revealed"

        prog = self._write_progress(trail, apply)
        result: dict[str, Any] = {"result": outcome["result"], "progress": to_json(prog)}
        if outcome["result"] == "hint":
            result["hint"] = self._render(cp, "hint")
        else:
            result["explanation"] = self._render(cp, "explanation")
            result["evidenceLines"] = cp.evidence_lines
            result["file"] = cp.file
            result["answer"] = cp.answer
        return result

    def checkpoint_skip(self, p: dict[str, Any], cancel: CancelToken) -> dict[str, Any]:
        cp_id = str(p["checkpointId"])
        trail = self._load_trail(cp_id.split(":", 1)[0])
        seg, _cp = trail.checkpoint(cp_id)

        def apply(prog: Progress) -> None:
            for st in prog.segments[seg.key].checkpoints.values():
                if st.state not in ("passed", "revealed"):
                    st.state = "skipped"

        return self._public(self._write_progress(trail, apply))

    def diff_count(self, p: dict[str, Any], cancel: CancelToken) -> dict[str, Any]:
        with self._lock:
            counts = count_changed_functions(self.engine, p.get("since") or None)
        counts["threshold"] = self.config.suggest_threshold
        return counts

    def progress_reset(self, p: dict[str, Any], cancel: CancelToken) -> dict[str, Any]:
        trail = self._load_trail(str(p["trailId"]))

        def apply(prog: Progress) -> None:
            for sp in prog.segments.values():
                sp.status = "todo"
                sp.checkpoints = {k: CheckpointState() for k in sp.checkpoints}

        return self._public(self._write_progress(trail, apply))

    def config_get(self, p: dict[str, Any], cancel: CancelToken) -> dict[str, Any]:
        return {"lang": self.lang, "provider": self.config.llm_provider, "model": self.config.llm_model,
                "endpoint": self.config.llm_endpoint, "hasKey": bool(self.config.api_key),
                "suggestThreshold": self.config.suggest_threshold}


METHODS: dict[str, Callable[[Session, dict[str, Any], CancelToken], Any]] = {
    "initialize": Session.initialize,
    "map.build": Session.map_build,
    "trail.build": Session.trail_build,
    "trail.current": Session.trail_current,
    "segment.guide": Session.segment_guide,
    "segment.code": Session.segment_code,
    "checkpoint.answer": Session.checkpoint_answer,
    "checkpoint.skip": Session.checkpoint_skip,
    "diff.count": Session.diff_count,
    "progress.reset": Session.progress_reset,
    "config.get": Session.config_get,
}
