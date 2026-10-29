"""Checkpoint generation and grading: flow, locate and diff_edge.

Every choice uses a seeded random generator (seed = snapshot + segment order), so the same
code always produces the same questions. Every answer can be recomputed from the graph:

* flow: of the options, the answer is the one ``A`` calls first (the others are called later
  or not at all). The "caller" variant asks which option calls ``A``.
* locate: the answer is a set of line ranges inside the segment's file.
* diff_edge: the answer is the only option with an added (or removed) edge to the target.

Texts are stored as i18n keys plus parameters and rendered in the viewer's language.
"""

from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ..i18n import render
from ..model import Checkpoint, Edge, GraphDiff, Map, Node, Option, Segment
from .index import MODULE_QUALNAME
from .parse import ParsedFile

OPTION_IDS = ("a", "b", "c", "d")
LOCATE_MIN_LINES = 10


def _rng(snapshot: str, order: int, salt: str = "") -> random.Random:
    digest = hashlib.sha256(f"{snapshot}:{order}:{salt}".encode()).hexdigest()
    return random.Random(int(digest[:16], 16))


@dataclass
class Context:
    map: Map
    files: dict[str, ParsedFile]
    edges: list[Edge]
    diff: GraphDiff | None = None
    base_callers: dict[str, set[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.index = self.map.node_index()
        self.calls_from: dict[str, list[Edge]] = defaultdict(list)
        self.callers_of: dict[str, list[Edge]] = defaultdict(list)
        for e in self.edges:
            if e.kind == "call" and e.dst is not None and e.resolved and not e.inferred and e.dst != e.src:
                self.calls_from[e.src].append(e)
                self.callers_of[e.dst].append(e)
        for v in self.calls_from.values():
            v.sort(key=lambda e: (e.line, e.dst or ""))

    def label(self, nid: str) -> str:
        n = self.index[nid]
        if n.qualname == MODULE_QUALNAME:
            pf = self.files.get(n.file)
            return pf.module if pf else n.file
        return n.qualname

    def long_label(self, nid: str) -> str:
        n = self.index[nid]
        pf = self.files.get(n.file)
        mod = pf.module if pf else n.file
        return f"{mod}.{n.qualname}" if n.qualname != MODULE_QUALNAME else mod

    def first_call_line(self, src: str, dst: str) -> int | None:
        lines = [e.line for e in self.calls_from.get(src, []) if e.dst == dst]
        return min(lines) if lines else None

    def callable(self, nid: str) -> bool:
        return self.index[nid].kind in ("function", "method", "class")


def _options(ctx: Context, rng: random.Random, answer: str, distractors: list[str]) -> tuple[list[Option], str]:
    chosen = [answer, *distractors[:3]]
    rng.shuffle(chosen)
    labels = [ctx.label(n) for n in chosen]
    options = []
    answer_id = ""
    for i, (nid, lab) in enumerate(zip(chosen, labels, strict=True)):
        if labels.count(lab) > 1:
            lab = ctx.long_label(nid)
        options.append(Option(id=OPTION_IDS[i], label=lab))
        if nid == answer:
            answer_id = OPTION_IDS[i]
    return options, answer_id


def _text(key: str, **params: Any) -> list[Any]:
    return [key, {k: str(v) for k, v in params.items()}]


def _finish(cp: Checkpoint) -> Checkpoint:
    """Fill the English strings from the i18n keys (clients re-render in their language)."""
    cp.prompt = render("en", *cp.text["prompt"])
    cp.hint = render("en", *cp.text["hint"])
    cp.explanation = " ".join(render("en", k, p) for k, p in cp.text["explanation"])
    return cp


def _unique(seq: list[str], exclude: set[str]) -> list[str]:
    out: list[str] = []
    for s in seq:
        if s not in exclude and s not in out:
            out.append(s)
    return out


# --------------------------------------------------------------------------- flow


def flow(ctx: Context, seg: Segment, next_nodes: list[str], cp_id: str, rng: random.Random) -> Checkpoint | None:
    a = seg.nodes[0]
    calls = ctx.calls_from.get(a, [])
    callees = list(dict.fromkeys(e.dst for e in calls if e.dst is not None and ctx.callable(e.dst)))
    if len(callees) <= 1:
        return None
    first_line = {c: ctx.first_call_line(a, c) or 0 for c in callees}
    answer = next((c for c in callees if c in next_nodes), None)
    if answer is None:
        answer = max(callees, key=lambda c: (ctx.index[c].h, -first_line[c]))
    ans_line = first_line[answer]
    later = sorted((c for c in callees if first_line[c] > ans_line), key=lambda c: first_line[c])
    a_node = ctx.index[a]
    a_callees = set(callees)
    same_module = sorted(
        (n.id for n in ctx.map.nodes if n.file == a_node.file and n.kind in ("function", "method")
         and n.id not in a_callees and n.id != a),
        key=lambda nid: (-ctx.index[nid].h, nid),
    )
    rng.shuffle(same_module)
    siblings: list[str] = []
    for caller_edge in ctx.callers_of.get(a, []):
        for e in ctx.calls_from.get(caller_edge.src, []):
            if e.dst and e.dst not in a_callees and e.dst != a and ctx.callable(e.dst):
                siblings.append(e.dst)
    distractors = _unique([*later, *same_module, *siblings], {answer, a})
    if not distractors:
        return None
    options, answer_id = _options(ctx, rng, answer, distractors)
    in_opts = [d for d in [answer, *distractors[:3]] if d != answer]
    called_later = [d for d in in_opts if d in first_line]
    expl = [_text("explain.flow", a=ctx.label(a), b=ctx.label(answer), line=ans_line)]
    if called_later:
        c = min(called_later, key=lambda d: first_line[d])
        expl.append(_text("explain.flow.later", c=ctx.label(c), line=first_line[c]))
    return _finish(Checkpoint(
        id=cp_id, type="flow", prompt="", node=a, options=options, answer=answer_id,
        evidence_lines=[ans_line, ans_line], file=a_node.file,
        text={"prompt": _text("cp.flow", a=ctx.label(a)),
              "hint": _text("hint.lines", start=a_node.start_line, end=a_node.end_line),
              "explanation": expl},
    ))


def caller(ctx: Context, seg: Segment, prev_nodes: list[str], cp_id: str, rng: random.Random) -> Checkpoint | None:
    """Fallback flow question for leaves: which option calls ``A``?"""
    a = seg.nodes[0]
    callers = list(dict.fromkeys(e.src for e in ctx.callers_of.get(a, [])))
    if not callers:
        return None
    answer = next((c for c in callers if c in prev_nodes), None) or max(
        callers, key=lambda c: (ctx.index[c].h, c))
    caller_set = set(callers)
    a_node = ctx.index[a]
    pool = sorted(
        (n.id for n in ctx.map.nodes if n.kind in ("function", "method") and n.id not in caller_set
         and n.id != a and ctx.calls_from.get(n.id)),
        key=lambda nid: (nid.split("::")[0] != a_node.file, -ctx.index[nid].h, nid),
    )[:12]
    rng.shuffle(pool)
    distractors = _unique(pool, {answer, a})
    if not distractors:
        return None
    options, answer_id = _options(ctx, rng, answer, distractors)
    line = ctx.first_call_line(answer, a) or 0
    ans_node = ctx.index[answer]
    return _finish(Checkpoint(
        id=cp_id, type="flow", prompt="", node=a, options=options, answer=answer_id,
        evidence_lines=[line, line], file=ans_node.file,
        text={"prompt": _text("cp.caller", a=ctx.label(a)),
              "hint": _text("hint.caller", a=ctx.label(a)),
              "explanation": [_text("explain.caller", c=ctx.label(answer), a=ctx.label(a), line=line,
                                    file=ans_node.file)]},
    ))


# --------------------------------------------------------------------------- locate


def _locate_candidates(ctx: Context, seg: Segment, next_nodes: list[str]) -> list[tuple[str, list[list[int]], dict[str, str]]]:
    a = seg.nodes[0]
    node = ctx.index[a]
    pf = ctx.files.get(node.file)
    out: list[tuple[str, list[list[int]], dict[str, str]]] = []
    for b in next_nodes:
        lines = sorted({e.line for e in ctx.calls_from.get(a, []) if e.dst == b})
        if lines:
            out.append(("call", [[ln, ln] for ln in lines], {"b": ctx.label(b)}))
            break
    if pf is None:
        return out
    owner = None if node.qualname == MODULE_QUALNAME else node.qualname
    spots = [s for s in pf.spots if s.owner == owner
             and node.start_line <= s.start_line <= node.end_line]
    raises = [[s.start_line, s.end_line] for s in spots if s.kind == "raise"]
    if raises:
        out.append(("raise", raises, {}))
    excepts = [[s.start_line, s.end_line] for s in spots if s.kind == "except"]
    if excepts:
        out.append(("except", excepts, {}))
    returns = [s for s in spots if s.kind == "return"]
    if len(returns) >= 2:
        early = [[s.start_line, s.end_line] for s in returns[:-1]]
        out.append(("return", early, {"a": ctx.label(a)}))
    return out


def locate(ctx: Context, seg: Segment, next_nodes: list[str], cp_id: str, rng: random.Random,
           allow_easy: bool = False) -> Checkpoint | None:
    a = seg.nodes[0]
    node = ctx.index[a]
    candidates = _locate_candidates(ctx, seg, next_nodes)
    if not candidates:
        return None
    if len(candidates) == 1 and node.loc < LOCATE_MIN_LINES and not allow_easy:
        return None
    kind, ranges, params = candidates[0] if candidates[0][0] == "call" else rng.choice(candidates)
    first = ranges[0]
    expl_key = {"call": "explain.locate.call", "raise": "explain.locate.raise",
                "except": "explain.locate.except", "return": "explain.locate.return"}[kind]
    return _finish(Checkpoint(
        id=cp_id, type="locate", prompt="", node=a, answer=ranges, evidence_lines=list(first),
        file=node.file,
        text={"prompt": _text(f"cp.locate.{kind}", **{"a": ctx.label(a), **params}),
              "hint": _text("hint.locate", start=node.start_line, end=node.end_line),
              "explanation": [_text(expl_key, **{"line": first[0], "start": first[0], "end": first[1],
                                                 "a": ctx.label(a), **params})]},
    ))


def locate_start(ctx: Context, seg: Segment, cp_id: str) -> Checkpoint:
    """Last resort so every segment has a static checkpoint: find where ``A`` starts."""
    a = seg.nodes[0]
    node = ctx.index[a]
    start = seg.start_line if node.qualname == MODULE_QUALNAME else node.start_line
    return _finish(Checkpoint(
        id=cp_id, type="locate", prompt="", node=a, answer=[[start, start]], evidence_lines=[start, start],
        file=node.file,
        text={"prompt": _text("cp.locate.start", a=ctx.label(a)),
              "hint": _text("hint.locate", start=seg.start_line, end=seg.end_line),
              "explanation": [_text("explain.locate.start", a=ctx.label(a), line=start)]},
    ))


# --------------------------------------------------------------------------- diff_edge


def diff_edge(ctx: Context, seg: Segment, cp_id: str, rng: random.Random) -> Checkpoint | None:
    if ctx.diff is None:
        return None
    nodes = set(seg.nodes)
    added = [e for e in ctx.diff.added_edges if e.src in nodes and e.dst in ctx.index and e.src in ctx.index]
    removed = [e for e in ctx.diff.removed_edges if e.src in nodes and e.src in ctx.index]
    # Only resolved edges are used (GraphDiff only carries resolved, non-inferred edges).
    choices: list[tuple[str, Any]] = [("added", e) for e in added] + [("removed", e) for e in removed]
    if not choices:
        return None
    kind, e = choices[0] if len(choices) == 1 else rng.choice(choices)
    target = e.dst
    src = e.src
    current_callers = {c.src for c in ctx.callers_of.get(target, [])} if target in ctx.index else set()
    base_callers = ctx.base_callers.get(target, set())
    added_srcs = {x.src for x in ctx.diff.added_edges if x.dst == target}
    removed_srcs = {x.src for x in ctx.diff.removed_edges if x.dst == target}
    if kind == "added":
        favored = sorted((c for c in base_callers & current_callers if c in ctx.index), key=lambda c: c)
        excluded = added_srcs
    else:
        favored = sorted((c for c in current_callers if c in ctx.index), key=lambda c: c)
        excluded = removed_srcs
    rng.shuffle(favored)
    others = sorted(
        (n.id for n in ctx.map.nodes if n.kind in ("function", "method") and n.id not in excluded
         and n.id != target and n.id != src),
        key=lambda nid: (nid.split("::")[0] != ctx.index[src].file, -ctx.index[nid].h, nid),
    )[:10]
    rng.shuffle(others)
    distractors = _unique([*favored, *others], excluded | {src, target})
    if not distractors:
        return None
    options, answer_id = _options(ctx, rng, src, distractors)
    t_label = ctx.label(target) if target in ctx.index else target.split("::")[-1]
    src_node = ctx.index[src]
    if kind == "added":
        prompt = _text("cp.diff.added", x=t_label)
        expl = [_text("explain.diff.added", s=ctx.label(src), x=t_label, line=e.line)]
        evidence = [e.line, e.line]
    else:
        prompt = _text("cp.diff.removed", y=t_label)
        expl = [_text("explain.diff.removed", s=ctx.label(src), y=t_label)]
        if target in ctx.diff.new_isolated:
            expl.append(_text("explain.diff.isolated", y=t_label))
        evidence = [src_node.start_line, src_node.end_line]
    return _finish(Checkpoint(
        id=cp_id, type="diff_edge", prompt="", node=src, options=options, answer=answer_id,
        evidence_lines=evidence, file=src_node.file,
        text={"prompt": prompt, "hint": _text("hint.lines", start=src_node.start_line, end=src_node.end_line),
              "explanation": expl},
    ))


# --------------------------------------------------------------------------- per trail


def generate(ctx: Context, segments: list[Segment], trail_key: str) -> None:
    """Attach 1–2 checkpoints to every segment (at least one static: flow or locate)."""
    snapshot = f"{ctx.map.repo.snapshot}:{trail_key}"
    main = [s for s in segments if not s.detour]
    for i, seg in enumerate(segments):
        rng = _rng(snapshot, seg.order)
        if seg.detour:
            later = [s for s in segments if s.order > seg.order]
        else:
            later = [s for s in main if s.order > seg.order]
        next_nodes = later[0].nodes if later else []
        earlier = [s for s in segments[:i] if not s.detour] or segments[:i]
        prev_nodes = earlier[-1].nodes if earlier else []
        base = f"{trail_key}:{seg.order}"
        cps: list[Checkpoint] = []
        if seg.changed:
            de = diff_edge(ctx, seg, f"{base}:d", rng)
            if de is not None:
                cps.append(de)
        static = (flow(ctx, seg, next_nodes, f"{base}:s", rng)
                  or locate(ctx, seg, next_nodes, f"{base}:s", rng)
                  or caller(ctx, seg, prev_nodes, f"{base}:s", rng)
                  or locate(ctx, seg, next_nodes, f"{base}:s", rng, allow_easy=True)
                  or locate_start(ctx, seg, f"{base}:s"))
        cps.append(static)
        if len(cps) == 1 and static.type == "flow" and ctx.index[seg.nodes[0]].loc >= 25:
            extra = locate(ctx, seg, next_nodes, f"{base}:l", rng)
            if extra is not None:
                cps.append(extra)
        seg.checkpoints = cps


# --------------------------------------------------------------------------- grading


def is_correct(cp: Checkpoint, answer: Any) -> bool:
    if cp.type == "locate":
        try:
            line = int(answer)
        except (TypeError, ValueError):
            return False
        return any(int(r[0]) <= line <= int(r[1]) for r in cp.answer)
    return isinstance(answer, str) and answer == cp.answer


def node_of(ctx: Context, nid: str) -> Node:
    return ctx.index[nid]
