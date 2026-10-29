"""Full and diff trails: summits, shortest paths from entry points, DFS order, grouping by
file, and detours beyond the segment limit."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

import networkx as nx

from ..model import GraphDiff, Map, Node, Segment
from . import graph as gr
from .index import MODULE_QUALNAME
from .parse import ParsedFile

MIN_SEGMENTS = 12


class NoChanges(Exception):
    """Only comments or whitespace changed (JSON-RPC -32003)."""


@dataclass
class _Draft:
    nodes: list[str]
    changed: bool = False
    isolated: bool = False
    detour: bool = False


def call_graph(g: nx.DiGraph) -> nx.DiGraph:
    """Calls plus references (functions passed as values, e.g. registered handlers): both are
    how control reaches code, so both make a reading order."""
    return nx.subgraph_view(g, filter_edge=lambda u, v: g[u][v].get("kind") in ("call", "ref"))


def _sources(m: Map) -> tuple[list[str], list[str]]:
    isolated = set(m.isolated)
    entries = [e for e in m.entries if e not in isolated]
    return entries, [r for r in m.library if r not in entries]


def _predecessors(gc: nx.DiGraph, entries: list[str], library: list[str]) -> tuple[dict[str, str | None], ...]:
    pred_entries, _ = gr.shortest_paths_from(gc, entries)
    pred_all, _ = gr.shortest_paths_from(gc, entries + library)
    return pred_entries, pred_all


def _path(target: str, preds: tuple[dict[str, str | None], ...], parent_of: dict[str, str]) -> list[str]:
    for pred in preds:
        if target in pred:
            return gr.path_to(pred, target)
    # Methods reached only through their class (instance calls the resolver cannot follow).
    parent = parent_of.get(target)
    if parent is not None:
        up = _path(parent, preds, parent_of)
        if up:
            return [*up, target]
    return [target]


def _parent_map(m: Map) -> dict[str, str]:
    out: dict[str, str] = {}
    for parent, members in gr.containment(m.nodes).items():
        for c in members:
            out[c] = parent
    return out


def _dfs_order(gc: nx.DiGraph, keep: set[str], starts: Iterable[str], index: dict[str, Node],
               parent_of: dict[str, str]) -> list[str]:
    children: dict[str, list[str]] = {}
    for c, p in parent_of.items():
        if c in keep and p in keep:
            children.setdefault(p, []).append(c)
    order: list[str] = []
    seen: set[str] = set()

    def visit(start: str) -> None:
        stack = [start]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            order.append(cur)
            nxt = [n for n in gr.ordered_successors(gc, cur) if n in keep] if cur in gc else []
            nxt += sorted(children.get(cur, []), key=lambda n: index[n].start_line)
            stack.extend(reversed([n for n in nxt if n not in seen]))

    for s in starts:
        if s in keep:
            visit(s)
    while len(seen) < len(keep):
        # Remaining pieces start at their roots (nodes nothing else in the piece calls).
        rest = [n for n in keep if n not in seen]
        rest_set = set(rest)
        roots = [n for n in rest if not any(p in rest_set for p in (gc.predecessors(n) if n in gc else []))]
        visit(min(roots or rest, key=lambda n: (-index[n].h, n)))
    return order


def _limit(drafts: list[_Draft], index: dict[str, Node], max_segments: int,
           protect: set[str]) -> list[_Draft]:
    """Group consecutive nodes of the same file, then turn the least important extra
    segments into detours, so at most ``max_segments`` segments are on the main trail."""
    def height(d: _Draft) -> float:
        return max(index[n].h for n in d.nodes)

    while len(drafts) > max_segments:
        best = None
        for i in range(len(drafts) - 1):
            a, b = drafts[i], drafts[i + 1]
            if index[a.nodes[0]].file == index[b.nodes[0]].file and a.isolated == b.isolated:
                score = height(a) + height(b)
                if best is None or score < best[0]:
                    best = (score, i)
        if best is None:
            break
        i = best[1]
        a, b = drafts[i], drafts[i + 1]
        drafts[i : i + 2] = [_Draft(nodes=a.nodes + b.nodes, changed=a.changed or b.changed, isolated=a.isolated)]
        if len(drafts) <= max_segments:
            break
    main = [d for d in drafts if not d.detour]
    if len(main) > max_segments:
        ranked = sorted(
            range(len(drafts)),
            key=lambda i: (
                any(n in protect for n in drafts[i].nodes),
                drafts[i].changed,
                height(drafts[i]),
                -i,
            ),
        )
        extra = len(main) - max_segments
        for i in ranked:
            if extra == 0:
                break
            if i == 0:  # the trail always starts at its first segment
                continue
            drafts[i].detour = True
            extra -= 1
    return drafts


def _module_lines(pf: ParsedFile | None, node: Node) -> tuple[int, int]:
    if pf is None:
        return node.start_line, min(node.end_line, node.start_line + 30)
    if "main_block" in pf.extra:
        start, end = pf.extra["main_block"]
        return int(start), int(end)
    lines = [c.line for c in pf.calls if c.caller is None]
    if lines:
        return min(lines), max(lines)
    return 1, min(node.end_line, 30)


def _segments(drafts: list[_Draft], index: dict[str, Node], files: dict[str, ParsedFile]) -> list[Segment]:
    out: list[Segment] = []
    for order, d in enumerate(drafts, start=1):
        main = index[d.nodes[0]]
        ranges = []
        for nid in d.nodes:
            n = index[nid]
            if n.qualname == MODULE_QUALNAME:
                ranges.append(_module_lines(files.get(n.file), n))
            else:
                ranges.append((n.start_line, n.end_line))
        title = main.qualname if main.qualname != MODULE_QUALNAME else main.file
        if len(d.nodes) > 1:
            title = f"{title} +{len(d.nodes) - 1}"
        out.append(Segment(order=order, title=title, file=main.file, start_line=min(r[0] for r in ranges),
                           end_line=max(r[1] for r in ranges), nodes=list(d.nodes), detour=d.detour,
                           changed=d.changed, isolated=d.isolated))
    return out


def full_trail(m: Map, g: nx.DiGraph, files: dict[str, ParsedFile], *, summits: int = 6,
               max_segments: int = 15) -> list[Segment]:
    index = m.node_index()
    gc = call_graph(g)
    parent_of = _parent_map(m)
    entries, library = _sources(m)
    preds = _predecessors(gc, entries, library)
    isolated = set(m.isolated)
    candidates = [n.id for n in sorted(m.nodes, key=lambda n: (-n.h, n.id))
                  if n.kind in gr.CALLABLE and n.id not in isolated]
    if not entries and not library and candidates:
        entries = candidates[:1]
        preds = _predecessors(gc, entries, [])
    k = max(1, summits)
    keep: set[str] = set()
    while True:
        keep = set()
        for s in candidates[:k]:
            keep.update(_path(s, preds, parent_of))
        if len(keep) >= MIN_SEGMENTS or k >= len(candidates):
            break
        k += 2
    starts = [e for e in entries + library if e in keep]
    order = _dfs_order(gc, keep, starts, index, parent_of)
    drafts = [_Draft(nodes=[n]) for n in order]
    protect = set(candidates[: max(1, summits)]) | set(entries)
    drafts = _limit(drafts, index, max_segments, protect)
    return _segments(drafts, index, files)


def diff_trail(m: Map, g: nx.DiGraph, files: dict[str, ParsedFile], diff: GraphDiff, *,
               max_segments: int = 15) -> list[Segment]:
    index = m.node_index()
    gc = call_graph(g)
    parent_of = _parent_map(m)
    touched = [n for n in diff.touched if n in index]
    lost_callers = [e.src for e in diff.removed_edges if e.src in index]
    core = list(dict.fromkeys([*touched, *lost_callers]))
    if not core and not diff.removed_nodes:
        raise NoChanges()
    entries, library = _sources(m)
    preds = _predecessors(gc, entries, library)
    keep: set[str] = set(core)
    path_nodes: set[str] = set()
    for c in core:
        path_nodes.update(_path(c, preds, parent_of))
    neighbors: set[str] = set()
    for c in core:
        if c in gc:
            neighbors.update(gc.predecessors(c))
            neighbors.update(gc.successors(c))
    new_isolated = {n for n in diff.new_isolated if n in index}
    keep |= path_nodes | neighbors | new_isolated
    keep = {n for n in keep if index[n].kind != "module" or n in path_nodes or n in core}
    starts = [e for e in entries + library if e in keep]
    order = _dfs_order(gc, keep - new_isolated, starts, index, parent_of)
    order += sorted(new_isolated - set(order), key=lambda n: (index[n].file, index[n].start_line))
    changed = set(core)
    drafts = [_Draft(nodes=[n], changed=n in changed, isolated=n in new_isolated) for n in order]
    # Neighbors that are not on a path from an entry point are the first to become detours.
    protect = changed | path_nodes | new_isolated
    drafts = _limit(drafts, index, max_segments, protect)
    return _segments(drafts, index, files)


def trail_id(kind: str, snapshot: str, extra: str = "") -> str:
    return hashlib.sha256(f"{kind}:{snapshot}:{extra}".encode()).hexdigest()[:12]
