import json
import os
from pathlib import Path

from thrubase.model import (
    Checkpoint,
    Edge,
    EdgeRef,
    GraphDiff,
    Map,
    Node,
    Option,
    Progress,
    Repo,
    Segment,
    SegmentProgress,
    Stats,
    Trail,
    from_json,
    json_schema,
    to_json,
)

SCHEMA_FILE = Path(__file__).parent.parent / "schema" / "thrubase.schema.json"


def sample_map() -> Map:
    return Map(
        repo=Repo(root="/r", name="r", snapshot="abc", files=1, skipped=0, languages=["python"]),
        nodes=[Node(id="a.py::f", kind="function", name="f", qualname="f", file="a.py", start_line=1,
                    end_line=2, loc=2, h=0.5, x=0.1, y=0.2, role="entry", entry_kind="script")],
        edges=[Edge(src="a.py::f", dst=None, kind="call", line=2, name="g", resolved=False)],
        entries=["a.py::f"], summits=[], isolated=[],
        stats=Stats(files=1, skipped_files=0, parse_errors=0, calls=1, external_calls=0, resolved_calls=0,
                    resolution_rate=0.0),
    )


def test_map_round_trip() -> None:
    m = sample_map()
    data = json.loads(json.dumps(to_json(m)))
    assert data["schema_version"] == 1
    back = from_json(Map, data)
    assert back == m
    assert back.node("a.py::f").role == "entry"


def test_trail_round_trip_and_public_hides_answers() -> None:
    cp = Checkpoint(id="t:1:s", type="flow", prompt="Which?", node="a.py::f",
                    options=[Option("a", "g"), Option("b", "h")], answer="a", evidence_lines=[2, 2],
                    hint="look", explanation="because", text={"prompt": ["cp.flow", {"a": "f"}]})
    diff = GraphDiff(base="HEAD", changed_files=["a.py"], added_nodes=[], removed_nodes=[], changed_nodes=["a.py::f"],
                     renamed={"a.py::old": "a.py::f"}, added_edges=[EdgeRef("a.py::f", "a.py::g", 3)],
                     removed_edges=[], new_isolated=[])
    trail = Trail(id="t", kind="diff", snapshot="abc",
                  segments=[Segment(order=1, title="f", file="a.py", start_line=1, end_line=2, nodes=["a.py::f"],
                                    checkpoints=[cp])],
                  path=["a.py::f"], diff=diff)
    back = from_json(Trail, json.loads(json.dumps(to_json(trail))))
    assert back == trail
    public = trail.public()
    pcp = public["segments"][0]["checkpoints"][0]
    for secret in ("answer", "explanation", "hint", "evidence_lines", "text"):
        assert secret not in pcp
    assert "because" not in json.dumps(public)


def test_progress_round_trip() -> None:
    p = Progress(trail_id="t", kind="full", segments={"k": SegmentProgress(key="k", status="passed")}, current=2)
    assert from_json(Progress, to_json(p)) == p


def test_json_schema_is_generated_and_committed() -> None:
    schema = json_schema()
    assert {"Map", "Trail", "Progress", "Node", "Edge", "Checkpoint"} <= set(schema["$defs"])
    text = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    if os.environ.get("THRUBASE_UPDATE_SCHEMA") or not SCHEMA_FILE.exists():
        SCHEMA_FILE.parent.mkdir(exist_ok=True)
        SCHEMA_FILE.write_text(text, encoding="utf-8")
    assert SCHEMA_FILE.read_text(encoding="utf-8") == text, "run with THRUBASE_UPDATE_SCHEMA=1"
