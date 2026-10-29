"""T5: checkpoint answers can be recomputed from the graph; no duplicate options.

Property test over random call graphs; ``THRUBASE_PROPERTY_EXAMPLES`` (CI: 1000) sets the count.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from gen import write_graph_repo
from thrubase.api import Session
from thrubase.engine import checkpoint as cpmod
from thrubase.model import Trail

EXAMPLES = int(os.environ.get("THRUBASE_PROPERTY_EXAMPLES", "60"))


@st.composite
def graphs(draw):  # type: ignore[no-untyped-def]
    n = draw(st.integers(min_value=3, max_value=30))
    edges = draw(st.lists(st.tuples(st.integers(0, n - 1), st.integers(0, n - 1)), min_size=n - 1,
                          max_size=n * 3))
    # Keep f0 connected to something so there is a trail.
    edges = [(0, 1), *[(a, b) for a, b in edges if a != b]]
    files = draw(st.integers(min_value=1, max_value=3))
    return n, edges, files


def check_trail(session: Session, trail: Trail) -> None:
    analysis = session._analysis()
    ctx = cpmod.Context(map=analysis.map, files={f.path: f for f in analysis.files}, edges=analysis.edges)
    main = [s for s in trail.segments if not s.detour]
    assert len(main) <= 15
    for seg in trail.segments:
        assert any(c.type in ("flow", "locate") for c in seg.checkpoints)
        assert 1 <= len(seg.checkpoints) <= 2
        a = seg.nodes[0]
        for cp in seg.checkpoints:
            ids = [o.id for o in cp.options]
            labels = [o.label for o in cp.options]
            assert len(set(ids)) == len(ids) and len(set(labels)) == len(labels)
            if cp.type == "flow":
                by_label = {ctx.label(n): n for n in ctx.index}
                by_label.update({ctx.long_label(n): n for n in ctx.index})
                nodes = {o.id: by_label[o.label] for o in cp.options}
                answer = nodes[cp.answer]
                if cp.text["prompt"][0] == "cp.flow":
                    first = {o: ctx.first_call_line(a, n) for o, n in nodes.items()}
                    called = {o: ln for o, ln in first.items() if ln is not None}
                    assert called[cp.answer] == min(called.values())
                    assert list(called.values()).count(called[cp.answer]) == 1
                else:  # caller variant
                    assert ctx.first_call_line(answer, a) is not None
                    for o, n in nodes.items():
                        if o != cp.answer:
                            assert ctx.first_call_line(n, a) is None
            elif cp.type == "locate":
                node = ctx.index[a]
                assert cp.file == node.file
                for start, end in cp.answer:
                    assert start <= end
                    assert cpmod.is_correct(cp, start) and cpmod.is_correct(cp, end)
                if cp.text["prompt"][0] == "cp.locate.call":
                    b_label = cp.text["prompt"][1]["b"]
                    lines = {e.line for e in ctx.calls_from[a] if ctx.label(str(e.dst)) == b_label}
                    assert {r[0] for r in cp.answer} == lines
                assert not cpmod.is_correct(cp, 10**6)


@settings(max_examples=EXAMPLES, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(graphs())
def test_random_graphs(g) -> None:  # type: ignore[no-untyped-def]
    n, edges, files = g
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "r"
        write_graph_repo(root, n, edges, files)
        session = Session(root)
        t = session.dispatch("trail.build", {"kind": "full"})
        trail = session._load_trail(t["id"])
        check_trail(session, trail)
        # Same input, same questions.
        again = Session(root).dispatch("trail.build", {"kind": "full"})
        t.pop("progress"), again.pop("progress")
        assert t == again


def test_grading() -> None:
    from thrubase.model import Checkpoint

    flow = Checkpoint(id="x", type="flow", prompt="", node="n", answer="b")
    assert cpmod.is_correct(flow, "b") and not cpmod.is_correct(flow, "a") and not cpmod.is_correct(flow, None)
    loc = Checkpoint(id="y", type="locate", prompt="", node="n", answer=[[3, 5], [9, 9]])
    assert [cpmod.is_correct(loc, x) for x in (2, 3, 5, 6, 9, "9", "x")] == [False, True, True, False, True, True,
                                                                            False]
