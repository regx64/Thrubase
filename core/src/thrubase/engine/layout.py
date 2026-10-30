"""Terrain map coordinates. Same input, same coordinates (byte for byte).

Two levels keep this fast at 2,000 files: files are laid out with a seeded
Fruchterman-Reingold spring layout (numpy), where high-altitude files are pulled toward
the center; each file's definitions then sit around the file's position on a golden-angle
spiral, highest altitude innermost. Coordinates are in 0..1 and rounded to 4 decimals.
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import numpy.typing as npt

from ..model import Edge, Node

SEED = 7
_GOLDEN = math.pi * (3 - math.sqrt(5))


DENSE_LIMIT = 400
SAMPLE = 192


Array = npt.NDArray[np.float64]


def _spring_sampled(n: int, adj: Array, gravity: Array, seed: int) -> Array:
    """Spring layout for many files: repulsion against a seeded random sample of nodes per
    iteration (O(n·s)), attraction along the sparse edges."""
    rng = np.random.default_rng(seed)
    pos = rng.random((n, 2))
    src, dst = np.nonzero(np.triu(adj))
    w = adj[src, dst]
    k = 1.0 / np.sqrt(n)
    iterations = 60
    temp = 0.1
    cool = temp / (iterations + 1)
    center = np.array([0.5, 0.5])
    scale = n / SAMPLE
    for _ in range(iterations):
        sample = rng.choice(n, size=SAMPLE, replace=False)
        delta = pos[:, None, :] - pos[sample][None, :, :]
        dist2 = (delta**2).sum(axis=-1)
        np.clip(dist2, 1e-4, None, out=dist2)
        disp = (delta * (k * k / dist2)[:, :, None]).sum(axis=1) * scale
        d = pos[src] - pos[dst]
        dist = np.sqrt((d**2).sum(axis=1))
        pull = d * (w * dist / k)[:, None]
        np.add.at(disp, src, -pull)
        np.add.at(disp, dst, pull)
        disp += (center - pos) * gravity[:, None]
        length = np.sqrt((disp**2).sum(axis=1))
        np.clip(length, 0.01, None, out=length)
        pos += disp * (np.minimum(length, temp) / length)[:, None]
        temp -= cool
    return pos


def _spring(n: int, adj: Array, gravity: Array, seed: int) -> Array:
    if n > DENSE_LIMIT:
        return _spring_sampled(n, adj, gravity, seed)
    rng = np.random.default_rng(seed)
    pos = rng.random((n, 2))
    if n == 1:
        return np.array([[0.5, 0.5]])
    k = 1.0 / math.sqrt(n)
    iterations = 120 if n <= 300 else 60
    temp = 0.1
    cool = temp / (iterations + 1)
    center = np.array([0.5, 0.5])
    for _ in range(iterations):
        delta = pos[:, None, :] - pos[None, :, :]
        dist = np.sqrt((delta**2).sum(axis=-1))
        np.clip(dist, 0.01, None, out=dist)
        force = (k * k / dist**2) - (adj * dist / k)
        disp = (delta * force[:, :, None]).sum(axis=1)
        disp += (center - pos) * gravity[:, None]
        length = np.sqrt((disp**2).sum(axis=1))
        np.clip(length, 0.01, None, out=length)
        pos += disp * (np.minimum(length, temp) / length)[:, None]
        temp -= cool
    return pos


def layout(nodes: list[Node], edges: list[Edge], seed: int = SEED) -> dict[str, tuple[float, float]]:
    by_file: dict[str, list[Node]] = defaultdict(list)
    for n in nodes:
        by_file[n.file].append(n)
    files = sorted(by_file)
    if not files:
        return {}
    fidx = {f: i for i, f in enumerate(files)}
    owner = {n.id: n.file for n in nodes}
    nf = len(files)
    adj = np.zeros((nf, nf))
    for e in edges:
        if e.dst is None or e.dst not in owner or e.src not in owner:
            continue
        a, b = fidx[owner[e.src]], fidx[owner[e.dst]]
        if a != b:
            adj[a, b] += 1
            adj[b, a] += 1
    top = float(np.max(adj)) if adj.size else 0.0
    if top > 0:
        adj = np.log1p(adj) / np.log1p(top)
    file_h = np.array([max((n.h for n in by_file[f]), default=0.0) for f in files])
    gravity = 0.02 + 0.6 * file_h**2
    centers = _spring(nf, adj, gravity, seed)

    # Spread the files evenly over a disc while keeping each file's direction and its rank by
    # distance from the middle: outliers (files nothing connects) no longer squeeze the rest
    # into a dot, and high-altitude files stay near the center.
    if nf > 1:
        rel = centers - centers.mean(axis=0)
        dist = np.sqrt((rel**2).sum(axis=1))
        order = np.argsort(dist, kind="stable")
        rank = np.empty(nf)
        rank[order] = np.arange(nf)
        ring = 0.42 * np.sqrt((rank + 0.5) / nf)
        heading = np.arctan2(rel[:, 1], rel[:, 0])
        centers = 0.5 + np.stack([ring * np.cos(heading), ring * np.sin(heading)], axis=1)

    total = sum(len(v) for v in by_file.values())
    out: dict[str, tuple[float, float]] = {}
    for f in files:
        members = sorted(by_file[f], key=lambda n: (-n.h, n.id))
        cx, cy = float(centers[fidx[f]][0]), float(centers[fidx[f]][1])
        radius = min(0.25, 0.35 * math.sqrt(len(members) / max(total, 1)) + 0.004 * math.sqrt(len(members)))
        for i, n in enumerate(members):
            if i == 0:
                x, y = cx, cy
            else:
                r = radius * math.sqrt(i / max(len(members) - 1, 1))
                angle = i * _GOLDEN
                x, y = cx + r * math.cos(angle), cy + r * math.sin(angle)
            out[n.id] = (round(min(max(float(x), 0.0), 1.0), 4), round(min(max(float(y), 0.0), 1.0), 4))
    return out
