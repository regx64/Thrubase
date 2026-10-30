"""T6: attempts, passed · weak · skipped, and progress surviving a rebuilt trail."""

from __future__ import annotations

from pathlib import Path

from thrubase.api import Session


def wrong_option(cp) -> str:  # type: ignore[no-untyped-def]
    return next(o.id for o in cp.options if o.id != cp.answer)


def wrong(cp):  # type: ignore[no-untyped-def]
    return wrong_option(cp) if cp.options else 10**6


def status(progress: dict, seg) -> str:  # type: ignore[no-untyped-def,type-arg]
    return progress["segments"][seg.key]["status"]


def test_grading_states(copy_fixture) -> None:  # type: ignore[no-untyped-def]
    root = copy_fixture("calls_app")
    s = Session(root)
    t = s.dispatch("trail.build", {"kind": "full"})
    trail = s._load_trail(t["id"])
    segs = [seg for seg in trail.segments if not seg.detour]
    assert t["progress"]["current"] == segs[0].order

    # Correct on the first try -> passed.
    for cp in segs[0].checkpoints:
        right = cp.answer if cp.options else cp.answer[0][0]
        res = s.dispatch("checkpoint.answer", {"checkpointId": cp.id, "answer": right})
        assert res["result"] == "correct"
        assert "explanation" in res
    assert status(res["progress"], segs[0]) == "passed"
    assert res["progress"]["current"] == segs[1].order

    # Wrong, then correct -> hint, then passed.
    cp = segs[1].checkpoints[0]
    res = s.dispatch("checkpoint.answer", {"checkpointId": cp.id, "answer": wrong(cp)})
    assert res["result"] == "hint" and res["hint"] and "answer" not in res and "explanation" not in res
    right = cp.answer if cp.options else cp.answer[0][0]
    res = s.dispatch("checkpoint.answer", {"checkpointId": cp.id, "answer": right})
    assert res["result"] == "correct"

    # Wrong twice -> revealed, segment weak.
    cp = segs[2].checkpoints[0]
    s.dispatch("checkpoint.answer", {"checkpointId": cp.id, "answer": wrong(cp)})
    res = s.dispatch("checkpoint.answer", {"checkpointId": cp.id, "answer": wrong(cp)})
    assert res["result"] == "revealed"
    assert res["answer"] == cp.answer and res["explanation"] and res["evidenceLines"]
    assert status(res["progress"], segs[2]) == "weak"
    # Answering again does not change a finished checkpoint.
    again = s.dispatch("checkpoint.answer", {"checkpointId": cp.id, "answer": right})
    assert again["result"] == "revealed"

    # Skip -> skipped.
    prog = s.dispatch("checkpoint.skip", {"checkpointId": segs[3].checkpoints[0].id})
    assert status(prog, segs[3]) == "skipped"

    # Progress is shared: a second session (another client) sees the same state.
    cur = Session(root).dispatch("trail.current", {})
    assert cur is not None and cur["trail"]["id"] == trail.id
    assert status(cur["progress"], segs[2]) == "weak"

    reset = s.dispatch("progress.reset", {"trailId": trail.id})
    assert all(v["status"] == "todo" for v in reset["segments"].values())


def test_progress_survives_small_edits(copy_fixture) -> None:  # type: ignore[no-untyped-def]
    root: Path = copy_fixture("calls_app")
    s = Session(root)
    t = s.dispatch("trail.build", {"kind": "full"})
    trail = s._load_trail(t["id"])
    first = trail.segments[0]
    for cp in first.checkpoints:
        s.dispatch("checkpoint.answer", {"checkpointId": cp.id, "answer": cp.answer if cp.options else cp.answer[0][0]})
    # A small edit somewhere else changes the snapshot and the trail id.
    p = root / "app" / "errors.py"
    p.write_text(p.read_text() + "\n\nclass Extra(Exception):\n    pass\n")
    s2 = Session(root)
    t2 = s2.dispatch("trail.build", {"kind": "full"})
    assert t2["id"] != t["id"]
    key = "|".join(sorted(first.nodes))
    assert t2["progress"]["segments"][key]["status"] == "passed"
    assert t2["progress"]["trail_id"] == t2["id"]
