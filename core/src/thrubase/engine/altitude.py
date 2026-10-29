"""Altitude h(v) = α·PageRank + β·in-degree + γ·LOC, each normalized to 0..1.

PageRank is computed here with numpy power iteration (no scipy), weighted by the number of
call sites, so the result is deterministic and has no extra dependency.

The PageRank term blends both edge directions (gate 1 tuning, see ``tests/golden/README.md``):
forward rank lifts what important code calls (shared helpers), reverse rank lifts what
drives the most code (``Session.request``, ``Flask.wsgi_app``). Forward-only rank put small
helpers such as ``Flask.ensure_sync`` at every summit, which reviewers did not read as core.
"""

from __future__ import annotations

import math

import networkx as nx
import numpy as np

DEFAULT_WEIGHTS = {"alpha": 0.5, "beta": 0.3, "gamma": 0.2}
#: share of forward PageRank in the PageRank term; the rest is reverse PageRank
FORWARD_SHARE = 0.25


def pagerank(g: nx.DiGraph, damping: float = 0.85, iterations: int = 100, tol: float = 1e-10) -> dict[str, float]:
    nodes = sorted(g.nodes)
    n = len(nodes)
    if n == 0:
        return {}
    idx = {v: i for i, v in enumerate(nodes)}
    src = np.fromiter((idx[u] for u, _ in g.edges), dtype=np.int64, count=g.number_of_edges())
    dst = np.fromiter((idx[v] for _, v in g.edges), dtype=np.int64, count=g.number_of_edges())
    w = np.fromiter((float(d.get("weight", 1)) for _, _, d in g.edges(data=True)), dtype=np.float64,
                    count=g.number_of_edges())
    out_w = np.bincount(src, weights=w, minlength=n) if len(src) else np.zeros(n)
    dangling = out_w == 0
    share = np.divide(w, out_w[src], out=np.zeros_like(w), where=out_w[src] > 0) if len(src) else w
    rank = np.full(n, 1.0 / n)
    for _ in range(iterations):
        flow = np.bincount(dst, weights=rank[src] * share, minlength=n) if len(src) else np.zeros(n)
        new = (1 - damping) / n + damping * (flow + rank[dangling].sum() / n)
        if float(np.abs(new - rank).sum()) < tol:
            rank = new
            break
        rank = new
    return {v: float(rank[i]) for v, i in idx.items()}


def _normalize(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    lo = min(values.values())
    hi = max(values.values())
    if hi - lo < 1e-15:
        return {k: (1.0 if hi > 0 else 0.0) for k in values}
    return {k: (v - lo) / (hi - lo) for k, v in values.items()}


def altitude(g: nx.DiGraph, loc: dict[str, int], weights: dict[str, float] | None = None,
             skip: set[str] | None = None) -> dict[str, float]:
    """Altitude for every node in ``g``. Nodes in ``skip`` (module nodes) are scored without
    LOC so whole files do not dominate the terrain."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    skip = skip or set()
    fwd = _normalize(pagerank(g))
    rev = _normalize(pagerank(g.reverse(copy=False)))
    pr = _normalize({v: FORWARD_SHARE * fwd.get(v, 0) + (1 - FORWARD_SHARE) * rev.get(v, 0) for v in g.nodes})
    indeg_raw = {v: math.log1p(len({u for u in g.predecessors(v) if u != v})) for v in g.nodes}
    indeg = _normalize(indeg_raw)
    loc_raw = {v: (0.0 if v in skip else math.log1p(loc.get(v, 0))) for v in g.nodes}
    locn = _normalize(loc_raw)
    raw = {v: w["alpha"] * pr.get(v, 0) + w["beta"] * indeg.get(v, 0) + w["gamma"] * locn.get(v, 0)
           for v in g.nodes}
    hi = max(raw.values(), default=0.0)
    if hi <= 0:
        return {v: 0.0 for v in g.nodes}
    return {v: round(x / hi, 6) for v, x in raw.items()}
