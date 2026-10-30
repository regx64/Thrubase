import os
from pathlib import Path

import pytest

from thrubase.adapters.base import default_registry
from thrubase.engine.collect import collect, is_included


def touch(root: Path, rel: str, text: str = "x = 1\n") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def test_includes_and_excludes(tmp_path: Path) -> None:
    for rel in ["pkg/__init__.py", "pkg/core.py", "pkg/sub/deep.py", "tests/test_core.py", "pkg/test_x.py",
                "conftest.py", ".venv/lib/site.py", "build/lib/pkg/core.py", "docs/conf.py", "node_modules/a.py",
                "pkg/data.txt", "secret/hidden.py", "pkg/gen_out.py", "pkg/sub/.gitignore"]:
        touch(tmp_path, rel)
    (tmp_path / ".gitignore").write_text("secret/\n*_out.py\n")
    (tmp_path / "pkg" / "sub" / ".gitignore").write_text("deep.py\n")
    c = collect(tmp_path, default_registry())
    assert c.paths == ["pkg/__init__.py", "pkg/core.py"]
    assert c.skipped == 0
    assert is_included(tmp_path, "pkg/new.py", default_registry())
    assert not is_included(tmp_path, "tests/test_new.py", default_registry())
    assert not is_included(tmp_path, "secret/x.py", default_registry())


def test_extra_excludes(tmp_path: Path) -> None:
    touch(tmp_path, "a.py")
    touch(tmp_path, "vendor/b.py")
    c = collect(tmp_path, default_registry(), extra_excludes=["vendor/"])
    assert c.paths == ["a.py"]


def test_file_cap_counts_skipped(tmp_path: Path) -> None:
    for i in range(12):
        touch(tmp_path, f"m{i:02}.py")
    touch(tmp_path, "deep/inner/z.py")
    c = collect(tmp_path, default_registry(), max_files=10)
    assert len(c.paths) == 10
    assert c.skipped == 3
    # Shallow files are kept first.
    assert "deep/inner/z.py" not in c.paths


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_symlinks_ignored(tmp_path: Path) -> None:
    touch(tmp_path, "real/a.py")
    (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
    (tmp_path / "b.py").symlink_to(tmp_path / "real" / "a.py")
    c = collect(tmp_path, default_registry())
    assert c.paths == ["real/a.py"]
    assert c.symlinks == 2
