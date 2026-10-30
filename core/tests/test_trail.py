"""T1/T4: full and diff trails."""

from __future__ import annotations

from pathlib import Path

from gen import write_graph_repo
from thrubase.api import Session

FIX = Path(__file__).parent / "fixtures"


def main_titles(trail: dict) -> list[str]:  # type: ignore[type-arg]
    return [s["title"] for s in trail["segments"] if not s["detour"]]


def test_full_trail_follows_call_order() -> None:
    t = Session(FIX / "calls_app").dispatch("trail.build", {"kind": "full"})
    assert main_titles(t) == [
        "main", "load_config", "parse_text", "Server.start", "Server.register", "health", "ping", "connect",
        "users", "fetch_users", "Server.loop", "Router.dispatch", "Router.find",
    ]
    assert t["segments"][0]["nodes"] == ["app/cli.py::main"]
    for s in t["segments"]:
        assert s["checkpoints"], s["title"]


def test_segment_cap_with_detours(tmp_path: Path) -> None:
    # A long chain plus side branches: 60 reachable functions.
    edges = [(i, i + 1) for i in range(40)] + [(i, 41 + i // 2) for i in range(0, 38, 2)]
    write_graph_repo(tmp_path / "r", 60, edges, files=4)
    t = Session(tmp_path / "r").dispatch("trail.build", {"kind": "full"})
    main = [s for s in t["segments"] if not s["detour"]]
    assert 12 <= len(main) <= 15
    assert t["segments"][0]["nodes"][0].endswith("::<module>") or not t["segments"][0]["detour"]
    orders = [s["order"] for s in t["segments"]]
    assert orders == sorted(orders) == list(range(1, len(orders) + 1))


def test_small_repo_has_fewer_segments(tmp_path: Path) -> None:
    write_graph_repo(tmp_path / "r", 4, [(0, 1), (1, 2), (1, 3)])
    t = Session(tmp_path / "r").dispatch("trail.build", {"kind": "full"})
    assert 1 <= len(t["segments"]) <= 6
    assert all(not s["detour"] for s in t["segments"])


def test_same_input_same_trail() -> None:
    a = Session(FIX / "calls_app").dispatch("trail.build", {"kind": "full"})
    b = Session(FIX / "calls_app").dispatch("trail.build", {"kind": "full"})
    a.pop("progress"), b.pop("progress")
    assert a == b
