"""Performance on a synthetic 2,000-file repository: first run 30 s, cached 2 s, under 1 GB."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

from perfgen import write_synthetic
from thrubase.engine.pipeline import Engine
from thrubase.store import Store

pytestmark = pytest.mark.perf


def peak_rss_mb() -> float:
    if sys.platform == "win32":  # pragma: no cover
        return 0.0
    import resource

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024) if sys.platform == "darwin" else peak / 1024


def test_two_thousand_files(tmp_path: Path) -> None:
    root = tmp_path / "big"
    write_synthetic(root, 2000)
    store = Store(tmp_path / "home")
    t0 = time.perf_counter()
    m = Engine(root, store=store).build_map()
    first = time.perf_counter() - t0
    assert m.stats.files == 2000
    t1 = time.perf_counter()
    m2 = Engine(root, store=store).build_map()  # a new process: disk caches only
    cached = time.perf_counter() - t1
    assert m2.repo.snapshot == m.repo.snapshot
    rss = peak_rss_mb()
    report = {"files": m.stats.files, "nodes": len(m.nodes), "edges": len(m.edges), "first_s": round(first, 2),
              "cached_s": round(cached, 2), "peak_rss_mb": round(rss)}
    out = os.environ.get("THRUBASE_PERF_REPORT")
    if out:
        Path(out).write_text(json.dumps(report, indent=2) + "\n")
    print(report)
    assert first < 30, report
    assert cached < 2, report
    assert rss < 1024, report
