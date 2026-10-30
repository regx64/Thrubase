"""T10/W1: every method over both transports (same tests), error codes, answers never exposed."""

from __future__ import annotations

import json
import shutil
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from clients import HttpClient, RemoteError, RpcClient
from conftest import git
from thrubase import SCHEMA_VERSION, __version__
from thrubase.api import NO_CHANGES, NO_SUPPORTED_LANGUAGE, NOT_A_GIT_REPOSITORY, SCHEMA_MISMATCH

FIX = Path(__file__).parent / "fixtures"
SECRET_KEYS = {"answer", "explanation", "hint", "evidence_lines", "text"}


@pytest.fixture(params=["rpc", "http"])
def client(request: pytest.FixtureRequest, copy_fixture) -> Iterator[Any]:  # type: ignore[no-untyped-def]
    root = copy_fixture("calls_app")
    c = RpcClient(root) if request.param == "rpc" else HttpClient(root)
    c.root_path = root  # type: ignore[attr-defined]
    try:
        yield c
    finally:
        c.close()


def walk_keys(obj: Any) -> set[str]:
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            out |= walk_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= walk_keys(v)
    return out


def test_all_methods(client: Any) -> None:
    init = client.initialize()
    assert init["serverVersion"] == __version__ and init["schemaVersion"] == SCHEMA_VERSION
    assert init["languages"] == ["python"]
    m = client.call("map.build", {})
    assert m["schema_version"] == SCHEMA_VERSION and m["entries"] == ["app/cli.py::main"]
    t = client.call("trail.build", {"kind": "full"})
    seg_keys = walk_keys(t["segments"])
    assert not (SECRET_KEYS & seg_keys), SECRET_KEYS & seg_keys
    assert t["progress"]["current"] == 1
    cur = client.call("trail.current", {})
    assert cur["trail"]["id"] == t["id"]
    assert client.call("segment.guide", {"trailId": t["id"], "order": 1}) == {"guide": None, "cached": False}
    code = client.call("segment.code", {"trailId": t["id"], "order": 1})
    assert code["file"] == "app/cli.py" and code["lines"] and code["startLine"] >= 1
    cp = t["segments"][0]["checkpoints"][0]
    answer: Any = cp["options"][0]["id"] if cp["options"] else 1
    res = client.call("checkpoint.answer", {"checkpointId": cp["id"], "answer": answer})
    assert res["result"] in ("correct", "hint")
    if res["result"] == "hint":
        assert "answer" not in res and "explanation" not in res
    skip = client.call("checkpoint.skip", {"checkpointId": t["segments"][1]["checkpoints"][0]["id"]})
    assert skip["trail_id"] == t["id"]
    reset = client.call("progress.reset", {"trailId": t["id"]})
    assert all(s["status"] == "todo" for s in reset["segments"].values())
    with pytest.raises(RemoteError) as exc:
        client.call("diff.count", {})
    assert exc.value.code == NOT_A_GIT_REPOSITORY
    with pytest.raises(RemoteError) as exc:
        client.call("no.such.method", {})
    assert exc.value.code == -32601


def test_diff_methods(client: Any) -> None:
    if shutil.which("git") is None:
        pytest.skip("git missing")
    root: Path = client.root_path
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    client.initialize()
    assert client.call("diff.count", {})["changedFunctions"] == 0
    with pytest.raises(RemoteError) as exc:
        client.call("trail.build", {"kind": "diff"})
    assert exc.value.code == NO_CHANGES
    p = root / "app" / "store.py"
    p.write_text(p.read_text().replace("return object()", "return dict()"))
    assert client.call("diff.count", {})["changedFunctions"] == 1
    t = client.call("trail.build", {"kind": "diff"})
    assert t["kind"] == "diff" and any(s["changed"] for s in t["segments"])
    assert not (SECRET_KEYS & walk_keys(t["segments"]))


def test_schema_mismatch(client: Any) -> None:
    with pytest.raises(RemoteError) as exc:
        client.call("initialize", {"schemaVersion": SCHEMA_VERSION + 1})
    assert exc.value.code == SCHEMA_MISMATCH


def test_unsupported_language(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text("hi")
    c = RpcClient(tmp_path)
    try:
        c.initialize()
        with pytest.raises(RemoteError) as exc:
            c.call("map.build", {})
        assert exc.value.code == NO_SUPPORTED_LANGUAGE
    finally:
        c.close()


def test_rpc_progress_notifications(copy_fixture) -> None:  # type: ignore[no-untyped-def]
    c = RpcClient(copy_fixture("calls_app"))
    try:
        c.initialize()
        c.call("map.build", {"noCache": True})
        stages = [n["params"]["stage"] for n in c.notifications if n["method"] == "$/progress"]
        assert stages[0] == "collect" and stages[-1] == "done" and "parse" in stages
    finally:
        c.close()


def test_rpc_cancellation(copy_fixture) -> None:  # type: ignore[no-untyped-def]
    c = RpcClient(copy_fixture("calls_app"))
    try:
        c.initialize()
        mid = c.request_id()
        # Cancel before the worker starts it: the request must answer -32800.
        c.send({"jsonrpc": "2.0", "method": "$/cancelRequest", "params": {"id": mid}})
        c.send({"jsonrpc": "2.0", "id": mid, "method": "map.build", "params": {"noCache": True}})
        with pytest.raises(RemoteError) as exc:
            c.wait(mid)
        assert exc.value.code == -32800
        # The server keeps working afterwards.
        assert c.call("map.build", {})["entries"] == ["app/cli.py::main"]
    finally:
        c.close()


def test_rpc_utf8_and_parse_error(copy_fixture) -> None:  # type: ignore[no-untyped-def]
    c = RpcClient(copy_fixture("calls_app"))
    try:
        res = c.call("initialize", {"root": str(c.root), "lang": "ko"})
        assert res["lang"] == "ko"
        t = c.call("trail.build", {"kind": "full"})
        assert "호출" in json.dumps(t, ensure_ascii=False)
        body = b"{not json"
        assert c.proc.stdin is not None
        c.proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        c.proc.stdin.flush()
        err = c.read()
        assert err["error"]["code"] == -32700
    finally:
        c.close()
