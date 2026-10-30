"""File collection: ``.gitignore`` (pathspec), adapter extensions and excludes, the file cap.

Paths are always POSIX and relative to the repository root. Symlinks are never followed.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass, field
from pathlib import Path

import pathspec

from ..adapters.base import LanguageAdapter, Registry

DEFAULT_MAX_FILES = 2000
_ALWAYS_SKIP_DIRS = frozenset({".git", ".hg", ".svn", "node_modules", "__pycache__"})


@dataclass
class Collected:
    root: Path
    files: list[tuple[str, LanguageAdapter]] = field(default_factory=list)
    #: files that matched an adapter but were left out by the file cap
    skipped: int = 0
    #: supported files excluded by .gitignore, adapter excludes or user excludes
    excluded: int = 0
    symlinks: int = 0

    @property
    def paths(self) -> list[str]:
        return [p for p, _ in self.files]


def _gitignore_lines(root: Path) -> list[str]:
    lines: list[str] = []
    gi = root / ".gitignore"
    for path in (gi, root / ".git" / "info" / "exclude"):
        if path.is_file():
            with contextlib.suppress(OSError):
                lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return lines


def _nested_gitignores(root: Path, rel_dir: str) -> list[str]:
    gi = root / rel_dir / ".gitignore"
    if not rel_dir or not gi.is_file():
        return []
    out = []
    try:
        for raw in gi.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            neg = line.startswith("!")
            body = line[1:] if neg else line
            anchored = body.startswith("/") or "/" in body.rstrip("/")
            prefix = f"{rel_dir}/" if anchored else f"{rel_dir}/**/"
            out.append(("!" if neg else "") + prefix + body.lstrip("/"))
    except OSError:
        pass
    return out


def collect(root: Path, registry: Registry, *, max_files: int = DEFAULT_MAX_FILES,
            extra_excludes: list[str] | None = None) -> Collected:
    root = root.resolve()
    result = Collected(root=root)
    gitignore_lines = _gitignore_lines(root)
    base_spec = pathspec.PathSpec.from_lines("gitignore", gitignore_lines)
    exclude_specs = {
        a.name: pathspec.PathSpec.from_lines("gitignore", [*a.excludes, *(extra_excludes or [])])
        for a in registry
    }
    found: list[tuple[str, LanguageAdapter]] = []

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        nested = _nested_gitignores(root, rel_dir)
        if nested:
            gitignore_lines.extend(nested)
            base_spec = pathspec.PathSpec.from_lines("gitignore", gitignore_lines)
        keep = []
        for d in sorted(dirnames):
            full = Path(dirpath) / d
            rel = f"{rel_dir}/{d}" if rel_dir else d
            if d in _ALWAYS_SKIP_DIRS or full.is_symlink():
                if full.is_symlink():
                    result.symlinks += 1
                continue
            if base_spec.match_file(rel + "/"):
                continue
            keep.append(d)
        dirnames[:] = keep
        for name in sorted(filenames):
            rel = f"{rel_dir}/{name}" if rel_dir else name
            adapter = registry.for_path(name)
            if adapter is None:
                continue
            if (Path(dirpath) / name).is_symlink():
                result.symlinks += 1
                continue
            if base_spec.match_file(rel) or exclude_specs[adapter.name].match_file(rel):
                result.excluded += 1
                continue
            found.append((rel, adapter))

    found.sort(key=lambda x: (x[0].count("/"), x[0]))
    result.files = sorted(found[:max_files], key=lambda x: x[0])
    result.skipped = max(0, len(found) - max_files)
    return result


def is_included(root: Path, rel: str, registry: Registry, extra_excludes: list[str] | None = None) -> bool:
    """Whether ``collect`` would analyze ``rel`` (used for files that exist only in a base revision)."""
    adapter = registry.for_path(rel.rsplit("/", 1)[-1])
    if adapter is None:
        return False
    parts = rel.split("/")
    if any(p in _ALWAYS_SKIP_DIRS for p in parts[:-1]):
        return False
    spec = pathspec.PathSpec.from_lines("gitignore", _gitignore_lines(root.resolve()))
    if spec.match_file(rel):
        return False
    return not pathspec.PathSpec.from_lines("gitignore", [*adapter.excludes, *(extra_excludes or [])]).match_file(rel)
