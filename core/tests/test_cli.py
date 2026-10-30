"""C11/T11/W3: CLI commands and exit codes."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from thrubase import __version__
from thrubase.cli import app

FIX = Path(__file__).parent / "fixtures"
runner = CliRunner()


def test_version() -> None:
    r = runner.invoke(app, ["--version"])
    assert r.exit_code == 0 and r.stdout.strip() == f"thrubase {__version__}"


def test_map_summary_and_json() -> None:
    r = runner.invoke(app, ["map", str(FIX / "calls_app")])
    assert r.exit_code == 0, r.stdout
    assert "Terrain map · calls_app" in r.stdout
    assert "Top 10 by altitude" in r.stdout
    assert "main" in r.stdout
    r = runner.invoke(app, ["map", str(FIX / "calls_app"), "--json", "--no-cache"])
    data = json.loads(r.stdout)
    assert data["entries"] == ["app/cli.py::main"]


def test_map_korean() -> None:
    r = runner.invoke(app, ["map", str(FIX / "calls_app"), "--lang", "ko"])
    assert "지형도 · calls_app" in r.stdout and "진입점" in r.stdout


def test_exit_codes(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("x")
    assert runner.invoke(app, ["map", str(tmp_path)]).exit_code == 3
    assert runner.invoke(app, ["map", str(tmp_path / "missing")]).exit_code == 2
    assert runner.invoke(app, ["map", "--bogus"]).exit_code == 2
    if shutil.which("git"):
        (tmp_path / "a.py").write_text("def f():\n    pass\n")
        assert runner.invoke(app, ["climb", str(tmp_path), "--diff"]).exit_code == 4
    assert runner.invoke(app, ["climb", str(tmp_path), "--lang", "fr"]).exit_code == 2


def test_config_commands(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    r = runner.invoke(app, ["config", "path"])
    assert r.exit_code == 0 and r.stdout.strip() == str(home / "config.toml")
    assert runner.invoke(app, ["config", "set", "llm.provider", "openai-compatible"]).exit_code == 0
    assert runner.invoke(app, ["config", "get", "llm.provider"]).stdout.strip() == "openai-compatible"
    monkeypatch.setenv("THRUBASE_LLM_PROVIDER", "anthropic")
    assert runner.invoke(app, ["config", "get", "llm.provider"]).stdout.strip() == "anthropic"
    assert runner.invoke(app, ["config", "set", "llm.provider", "nope"]).exit_code == 2
    assert runner.invoke(app, ["config", "get", "bogus"]).exit_code == 2
    assert runner.invoke(app, ["config", "get", "analysis.extra_excludes"]).stdout.strip() == "[]"


def test_climb_paused_on_eof(copy_fixture) -> None:  # type: ignore[no-untyped-def]
    root = copy_fixture("calls_app")
    r = runner.invoke(app, ["climb", str(root)], input="")
    assert r.exit_code == 0
    assert "Climb paused" in r.stdout


def test_remove_tree_read_only(tmp_path: Path) -> None:
    import os
    import stat

    from thrubase.cli import remove_tree

    d = tmp_path / "clone" / ".git" / "objects"
    d.mkdir(parents=True)
    f = d / "pack"
    f.write_text("x")
    os.chmod(f, stat.S_IREAD)
    remove_tree(tmp_path / "clone")
    assert not (tmp_path / "clone").exists()
