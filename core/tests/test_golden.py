"""Golden values for the validation repositories (gate 1/2 review results).

Needs THRUBASE_VALIDATION_DIR (see tests/validation/fetch.py). Intended changes are written
with ``pytest --update-golden`` and reviewed in the PR.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from thrubase.api import Session

GOLDEN = Path(__file__).parent / "golden"
VALIDATION = os.environ.get("THRUBASE_VALIDATION_DIR")
REPOS = ["flask", "requests", "ai-service"]

pytestmark = [
    pytest.mark.golden,
    pytest.mark.skipif(not VALIDATION, reason="THRUBASE_VALIDATION_DIR is not set"),
]


def observe(root: Path) -> dict[str, Any]:
    session = Session(root, lang="en")
    m = session.dispatch("map.build", {"noCache": True})
    nodes = {n["id"]: n for n in m["nodes"]}
    top = sorted((n for n in m["nodes"] if n["kind"] != "module"), key=lambda n: (-n["h"], n["id"]))[:10]
    trail = session.dispatch("trail.build", {"kind": "full"})
    return {
        "entries": sorted(f"{nodes[e]['file']}::{nodes[e]['qualname']} ({nodes[e]['entry_kind']})"
                          for e in m["entries"]),
        "top10": [f"{n['file']}::{n['qualname']}" for n in top],
        "resolution_rate": round(m["stats"]["resolution_rate"], 3),
        "files": m["stats"]["files"],
        "trail": [("detour: " if s["detour"] else "") + s["title"] for s in trail["segments"]],
        "checkpoints_per_segment": sorted({len(s["checkpoints"]) for s in trail["segments"]}),
    }


@pytest.mark.parametrize("name", REPOS)
def test_golden(name: str, update_golden: bool) -> None:
    assert VALIDATION
    root = Path(VALIDATION) / name
    if not root.is_dir():
        pytest.skip(f"{root} missing; run tests/validation/fetch.py")
    got = observe(root)
    path = GOLDEN / f"{name}.json"
    if update_golden or not path.exists():
        old = json.loads(path.read_text()) if path.exists() else {}
        out = {**got, "review": old.get("review", "pending human review")}
        path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
        if not update_golden:
            pytest.fail(f"wrote {path}; review it and commit")
    want = json.loads(path.read_text())
    want.pop("review", None)
    # Definition of done: at least one entry point, 12–15 main segments, a checkpoint on each.
    assert got["entries"]
    main = [t for t in got["trail"] if not t.startswith("detour: ")]
    assert 12 <= len(main) <= 15
    assert min(got["checkpoints_per_segment"]) >= 1
    assert got == want
