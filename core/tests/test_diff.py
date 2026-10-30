"""T2/T3/T4: change detection, base-revision analysis, GraphDiff, diff trails, diff.count."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import git
from gen import write_graph_repo
from thrubase.api import NO_CHANGES, NOT_A_GIT_REPOSITORY, ApiError, Session
from thrubase.engine.diff import NotARepository, count_changed_functions, detect_changes, graph_diff
from thrubase.engine.pipeline import Engine
from thrubase.store import Store

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")


def edit(root: Path, rel: str, old: str, new: str) -> None:
    p = root / rel
    text = p.read_text()
    assert old in text, (rel, old)
    p.write_text(text.replace(old, new))


def changes(root: Path, since: str | None = None) -> set[tuple[str, str, str | None]]:
    _, ch = detect_changes(root, since)
    return {(c.status, c.path, c.old_path) for c in ch}


def test_detects_add_edit_delete_rename_staged(git_repo: Path) -> None:
    edit(git_repo, "app/router.py", "return body.upper()", "return body.lower()")
    (git_repo / "app" / "new.py").write_text("def fresh():\n    return 1\n")
    (git_repo / "app" / "errors.py").unlink()
    git(git_repo, "mv", "app/store.py", "app/storage.py")
    edit(git_repo, "app/config.py", "out = {}", "out: dict[str, str] = {}")
    git(git_repo, "add", "app/config.py")  # staged
    got = changes(git_repo)
    assert ("M", "app/router.py", None) in got
    assert ("A", "app/new.py", None) in got
    assert ("D", "app/errors.py", None) in got
    assert ("R", "app/storage.py", "app/store.py") in got
    assert ("M", "app/config.py", None) in got


def test_since_ref(git_repo: Path) -> None:
    edit(git_repo, "app/router.py", "return body.upper()", "return body.lower()")
    git(git_repo, "commit", "-qam", "second")
    assert changes(git_repo) == set()
    assert changes(git_repo, "HEAD~1") == {("M", "app/router.py", None)}


def test_empty_repository(tmp_path: Path) -> None:
    root = tmp_path / "r"
    root.mkdir()
    (root / "a.py").write_text("def f():\n    return 1\n")
    git(root, "init", "-q")
    assert changes(root) == {("A", "a.py", None)}
    counts = count_changed_functions(Engine(root))
    assert counts == {"changedFunctions": 1, "changedFiles": 1}


def test_not_a_repository(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n")
    with pytest.raises(NotARepository):
        detect_changes(tmp_path)
    with pytest.raises(ApiError) as exc:
        Session(tmp_path).dispatch("diff.count", {})
    assert exc.value.code == NOT_A_GIT_REPOSITORY


def test_graph_diff_edit_add_remove_rename(git_repo: Path) -> None:
    # edit a body
    edit(git_repo, "app/router.py", "return body.upper()", "return body.lower()")
    # rename with the same body (and update the caller)
    edit(git_repo, "app/store.py", "def ping() -> bool:", "def is_alive() -> bool:")
    edit(git_repo, "app/handlers.py", "import fetch_users, ping", "import fetch_users, is_alive")
    edit(git_repo, "app/handlers.py", "if not ping():", "if not is_alive():")
    # add a function and a call to it; remove a call
    (git_repo / "app" / "metrics.py").write_text("def count_request() -> None:\n    return None\n")
    edit(git_repo, "app/server.py", "from .router import Router",
         "from .router import Router\nfrom .metrics import count_request")
    edit(git_repo, "app/server.py", "        request = self.accept()\n",
         "        request = self.accept()\n        count_request()\n")
    edit(git_repo, "app/config.py", "    validate(data)\n", "")
    engine = Engine(git_repo)
    analysis = engine.analyze()
    d = graph_diff(engine, analysis).diff
    assert "app/router.py::encode" in d.changed_nodes
    assert d.renamed == {"app/store.py::ping": "app/store.py::is_alive"}
    assert "app/metrics.py::count_request" in d.added_nodes
    assert ("app/server.py::Server.loop", "app/metrics.py::count_request") in {(e.src, e.dst) for e in d.added_edges}
    assert ("app/config.py::load_config", "app/config.py::validate") in {(e.src, e.dst) for e in d.removed_edges}
    assert "app/config.py::validate" in d.new_isolated
    # The renamed function keeps its callers: no added/removed edge for health -> ping/is_alive.
    pairs = {(e.src, e.dst) for e in d.added_edges + d.removed_edges}
    assert ("app/handlers.py::health", "app/store.py::is_alive") not in pairs


def test_only_changed_files_are_reparsed(tmp_path: Path) -> None:
    root = tmp_path / "r"
    write_graph_repo(root, 50, [(i, i + 1) for i in range(49)], files=49)  # 49 modules + __init__ = 50 files
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    store = Store(tmp_path / "home")
    Engine(root, store=store).build_map()
    edit(root, "pkg/m3.py", "    return 3", "    return 33")
    edit(root, "pkg/m7.py", "    return 7", "    return 77")
    engine = Engine(root, store=store)  # a new process: only the disk cache is shared
    analysis = engine.analyze()
    assert engine.parser.count == 2
    res = graph_diff(engine, analysis)
    assert engine.parser.count == 4  # 2 changed files × (current + base)
    assert res.diff.changed_nodes == ["pkg/m3.py::f3", "pkg/m7.py::f7"]


def test_diff_trail_reaches_an_entry_point(git_repo: Path) -> None:
    edit(git_repo, "app/store.py", "    return object()", "    return dict()")
    session = Session(git_repo)
    t = session.dispatch("trail.build", {"kind": "diff"})
    nodes = [n for s in t["segments"] for n in s["nodes"]]
    assert t["segments"][0]["nodes"][0] == "app/cli.py::main"
    assert "app/store.py::connect" in nodes
    changed = [s for s in t["segments"] if s["changed"]]
    assert [s["nodes"][0] for s in changed] == ["app/store.py::connect"]
    assert t["diff"]["changed_nodes"] == ["app/store.py::connect"]


def test_diff_edge_questions(git_repo: Path) -> None:
    edit(git_repo, "app/handlers.py", "    if not ping():\n        return \"down\"\n", "")
    edit(git_repo, "app/handlers.py", "    rows = fetch_users()\n", "    rows = fetch_users()\n    ping()\n")
    session = Session(git_repo)
    t = session.dispatch("trail.build", {"kind": "diff"})
    full = session._load_trail(t["id"])
    dcps = [c for s in full.segments for c in s.checkpoints if c.type == "diff_edge"]
    prompts = {c.text["prompt"][0]: c for c in dcps}
    assert "cp.diff.added" in prompts and "cp.diff.removed" in prompts
    added = prompts["cp.diff.added"]
    assert [o.label for o in added.options if o.id == added.answer] == ["users"]
    removed = prompts["cp.diff.removed"]
    assert [o.label for o in removed.options if o.id == removed.answer] == ["health"]
    # Answering through the API grades in core.
    res = session.dispatch("checkpoint.answer", {"checkpointId": added.id, "answer": added.answer})
    assert res["result"] == "correct"


def test_comment_only_change_is_no_change(git_repo: Path) -> None:
    edit(git_repo, "app/store.py", "def connect() -> object:\n", "def connect() -> object:\n    # just a note\n")
    with pytest.raises(ApiError) as exc:
        Session(git_repo).dispatch("trail.build", {"kind": "diff"})
    assert exc.value.code == NO_CHANGES
    assert Session(git_repo).dispatch("diff.count", {})["changedFunctions"] == 0


def test_diff_count(git_repo: Path) -> None:
    edit(git_repo, "app/store.py", "    return object()", "    return dict()")
    edit(git_repo, "app/store.py", "    return []", "    return [sql]")
    edit(git_repo, "app/router.py", "from .errors import RouteError", "from .errors import RouteError\nimport os")
    (git_repo / "app" / "extra.py").write_text("def a():\n    pass\n\n\ndef b():\n    pass\n")
    (git_repo / "README.md").write_text("docs\n")
    counts = Session(git_repo).dispatch("diff.count", {})
    # connect + query changed, a + b added; router.py only changed imports and is not counted.
    assert counts["changedFunctions"] == 4
    assert counts["changedFiles"] == 2
    assert counts["threshold"] == 5
