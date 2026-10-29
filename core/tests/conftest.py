from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from thrubase.store import Store

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN = Path(__file__).parent / "golden"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--update-golden", action="store_true", help="rewrite tests/golden/*.json")


@pytest.fixture
def update_golden(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--update-golden"))


@pytest.fixture(autouse=True)
def home(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test gets its own THRUBASE_HOME and a clean environment."""
    h = tmp_path_factory.mktemp("home")
    monkeypatch.setenv("THRUBASE_HOME", str(h))
    for var in ("THRUBASE_LANG", "THRUBASE_LLM_PROVIDER", "THRUBASE_LLM_MODEL", "THRUBASE_LLM_ENDPOINT",
                "THRUBASE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LANG", "C.UTF-8")
    return h


@pytest.fixture
def store(home: Path) -> Store:
    return Store(home)


def fixture_copy(name: str, dest: Path) -> Path:
    target = dest / Path(name).name
    shutil.copytree(FIXTURES / name, target)
    return target


@pytest.fixture
def copy_fixture(tmp_path: Path):  # type: ignore[no-untyped-def]
    def _copy(name: str) -> Path:
        return fixture_copy(name, tmp_path)

    return _copy


def git(root: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=True, env=env)
    return out.stdout.decode()


@pytest.fixture
def git_repo(tmp_path: Path) -> Iterator[Path]:
    """calls_app committed into a fresh git repository."""
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    root = fixture_copy("calls_app", tmp_path)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    yield root
