"""C9: same input, same coordinates (byte for byte)."""

import json
import subprocess
import sys
from pathlib import Path

from thrubase.engine.pipeline import Engine
from thrubase.store import Store

FIX = Path(__file__).parent / "fixtures"


def coords(store: Store) -> str:
    m = Engine(FIX / "calls_app", store=store).build_map(no_cache=True)
    return json.dumps({n.id: [n.x, n.y] for n in m.nodes}, sort_keys=True)


def test_two_runs_identical(store: Store) -> None:
    a = coords(store)
    b = coords(store)
    assert a == b
    data = json.loads(a)
    assert all(0 <= x <= 1 and 0 <= y <= 1 for x, y in data.values())


def test_identical_across_processes(tmp_path: Path) -> None:
    code = (
        "import json,sys;from pathlib import Path;from thrubase.engine.pipeline import Engine;"
        "from thrubase.store import Store;"
        f"m=Engine(Path({str(FIX / 'calls_app')!r}),store=Store(Path(sys.argv[1]))).build_map(no_cache=True);"
        "print(json.dumps({n.id:[n.x,n.y] for n in m.nodes},sort_keys=True))"
    )
    outs = [subprocess.run([sys.executable, "-c", code, str(tmp_path / f"h{i}")], capture_output=True,
                           check=True, text=True).stdout for i in range(2)]
    assert outs[0] == outs[1]


def test_summits_near_center(store: Store) -> None:
    m = Engine(FIX / "calls_app", store=store).build_map(no_cache=True)
    def dist(n):  # type: ignore[no-untyped-def]
        return ((n.x - 0.5) ** 2 + (n.y - 0.5) ** 2) ** 0.5
    top = max(m.nodes, key=lambda n: n.h)
    low = min(m.nodes, key=lambda n: n.h)
    assert dist(top) <= dist(low) + 0.25
