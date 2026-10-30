"""Call graph (networkx DiGraph) and isolated-zone detection."""

from __future__ import annotations

from collections import deque

import networkx as nx

from ..model import Edge, Node

CALLABLE = ("function", "method", "class")
_RANK = {"call": 0, "inherit": 1, "ref": 2}


def build_graph(nodes: list[Node], edges: list[Edge]) -> nx.DiGraph:
    """Nodes keyed by id; one edge per (src, dst) with ``weight`` = number of call sites and
    ``lines`` = the call lines. Edges with an unknown target are left out."""
    g = nx.DiGraph()
    for n in nodes:
        g.add_node(n.id, kind=n.kind, file=n.file)
    for e in edges:
        if e.dst is None or e.dst == e.src or e.dst not in g or e.src not in g:
            continue
        if g.has_edge(e.src, e.dst):
            data = g[e.src][e.dst]
            data["weight"] += 1
            data["lines"].append(e.line)
            data["resolved"] = data["resolved"] or (e.resolved and not e.inferred)
            if _RANK[e.kind] < _RANK[data["kind"]]:
                data["kind"] = e.kind
        else:
            g.add_edge(e.src, e.dst, weight=1, lines=[e.line], kind=e.kind,
                       resolved=e.resolved and not e.inferred)
    return g


def containment(nodes: list[Node]) -> dict[str, list[str]]:
    """parent id -> member ids (class -> methods, function -> nested functions)."""
    out: dict[str, list[str]] = {}
    for n in nodes:
        if n.kind == "module":
            continue
        path, _, qual = n.id.rpartition("::")
        parent_qual = qual.rpartition(".")[0]
        if parent_qual:
            out.setdefault(f"{path}::{parent_qual}", []).append(n.id)
    return out


def reachable(g: nx.DiGraph, entries: list[str], members: dict[str, list[str]]) -> set[str]:
    """Everything reachable from the entry points through calls and inheritance. A reached
    class also reaches its methods, since instance methods are usually called through
    attributes the resolver cannot follow."""
    parent = {c: p for p, cs in members.items() for c in cs}
    seen: set[str] = set()
    queue = deque(e for e in entries if e in g)
    seen.update(queue)
    while queue:
        cur = queue.popleft()
        # A reached class reaches its methods; a reached function its nested functions; a
        # reached method (``C()`` resolves to ``C.__init__``) its class.
        nxt = list(g.successors(cur)) + members.get(cur, [])
        if g.nodes[cur].get("kind") == "method" and cur in parent:
            nxt.append(parent[cur])
        for n in nxt:
            if n not in seen:
                seen.add(n)
                queue.append(n)
    return seen


def isolated_zones(g: nx.DiGraph, entries: list[str], members: dict[str, list[str]]) -> list[str]:
    """Callable nodes nothing reachable calls. Without entry points nothing is called isolated."""
    if not entries:
        return []
    seen = reachable(g, entries, members)
    return sorted(n for n, d in g.nodes(data=True) if d.get("kind") in CALLABLE and n not in seen)


def shortest_paths_from(g: nx.DiGraph, sources: list[str]) -> tuple[dict[str, str | None], dict[str, int]]:
    """Multi-source BFS over call edges. Returns predecessor and depth maps; the order of
    ``sources`` and of successors (sorted by first call line) makes it deterministic."""
    pred: dict[str, str | None] = {}
    depth: dict[str, int] = {}
    queue: deque[str] = deque()
    for s in sources:
        if s in g and s not in pred:
            pred[s] = None
            depth[s] = 0
            queue.append(s)
    while queue:
        cur = queue.popleft()
        for n in ordered_successors(g, cur):
            if n not in pred:
                pred[n] = cur
                depth[n] = depth[cur] + 1
                queue.append(n)
    return pred, depth


def ordered_successors(g: nx.DiGraph, node: str) -> list[str]:
    """Callees in source order (first call line), then id for ties."""
    return sorted(g.successors(node), key=lambda n: (min(g[node][n]["lines"]), n))


def path_to(pred: dict[str, str | None], target: str) -> list[str]:
    if target not in pred:
        return []
    out = [target]
    cur = pred[target]
    while cur is not None:
        out.append(cur)
        cur = pred[cur]
    return out[::-1]
