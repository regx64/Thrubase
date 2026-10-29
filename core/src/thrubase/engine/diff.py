"""Git change detection, base-revision analysis and GraphDiff.

Only changed files are parsed at the base revision (``git show <ref>:<path>``); every other
file reuses the current analysis. Paths stay POSIX and relative to the analyzed root.
"""

from __future__ import annotations

import dataclasses
import difflib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..model import Edge, EdgeRef, GraphDiff
from . import graph as gr
from .collect import is_included
from .index import SymbolIndex
from .parse import ParsedFile
from .pipeline import Analysis, Engine, _nodes

RENAME_SIMILARITY = 0.8


class GitError(Exception):
    pass


class GitMissing(GitError):
    pass


class NotARepository(GitError):
    """Exit code 4 / JSON-RPC -32002."""


class BadRevision(GitError):
    pass


@dataclass
class Change:
    status: str  # A M D R
    path: str
    old_path: str | None = None


def _git(root: Path, *args: str, check: bool = True) -> bytes:
    exe = shutil.which("git")
    if exe is None:
        raise GitMissing("git was not found on PATH")
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "LC_ALL": "C"}
    proc = subprocess.run([exe, "-C", str(root), *args], capture_output=True, env=env, check=False)
    if check and proc.returncode != 0:
        raise GitError(proc.stderr.decode("utf-8", "replace").strip())
    return proc.stdout


def ensure_repository(root: Path) -> None:
    try:
        out = _git(root, "rev-parse", "--is-inside-work-tree", check=False)
    except GitMissing:
        raise
    if out.strip() != b"true":
        raise NotARepository(str(root))


def has_head(root: Path) -> bool:
    return bool(_git(root, "rev-parse", "--verify", "-q", "HEAD", check=False).strip())


def verify_ref(root: Path, ref: str) -> None:
    if not _git(root, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}", check=False).strip():
        raise BadRevision(ref)


def _split_z(data: bytes) -> list[str]:
    return [p.decode("utf-8", "surrogateescape") for p in data.split(b"\0") if p]


def detect_changes(root: Path, since: str | None = None) -> tuple[str | None, list[Change]]:
    """Working tree (staged, unstaged and new files) against ``since`` (default ``HEAD``).
    Returns the base ref actually used (None for a repository without commits) and changes."""
    ensure_repository(root)
    base: str | None = since or "HEAD"
    if since:
        verify_ref(root, since)
    elif not has_head(root):
        base = None
    changes: list[Change] = []
    if base is None:
        for p in _split_z(_git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")):
            changes.append(Change("A", p))
        return None, changes
    items = _split_z(_git(root, "diff", "-z", "--name-status", "-M", "--relative", base, "--"))
    i = 0
    while i < len(items):
        status = items[i]
        code = status[0]
        if code == "R" or code == "C":
            old, new = items[i + 1], items[i + 2]
            changes.append(Change("R" if code == "R" else "A", new, old if code == "R" else None))
            i += 3
            continue
        path = items[i + 1]
        if code in ("A", "M", "D"):
            changes.append(Change(code, path))
        elif code == "T":
            changes.append(Change("M", path))
        i += 2
    for p in _split_z(_git(root, "ls-files", "-z", "--others", "--exclude-standard")):
        changes.append(Change("A", p))
    seen: dict[str, Change] = {}
    for c in changes:
        seen.setdefault(c.path, c)
    return base, sorted(seen.values(), key=lambda c: c.path)


def base_source(root: Path, ref: str | None, path: str) -> bytes | None:
    if ref is None:
        return None
    try:
        return _git(root, "show", f"{ref}:./{path}")
    except GitError:
        return None


# --------------------------------------------------------------------------- analysis


def _relevant(engine: Engine, changes: list[Change]) -> list[Change]:
    out = []
    for c in changes:
        paths = [c.path] + ([c.old_path] if c.old_path else [])
        if any(is_included(engine.root, p, engine.registry, engine.config.extra_excludes) for p in paths):
            out.append(c)
    return out


def _base_files(engine: Engine, current: list[ParsedFile], base: str | None,
                changes: list[Change]) -> tuple[list[ParsedFile], dict[str, ParsedFile]]:
    """Base revision files: unchanged files are reused, changed ones are parsed from git."""
    files = {pf.path: pf for pf in current}
    base_sources: dict[str, bytes] = {}
    for c in changes:
        if c.status in ("A", "R"):
            files.pop(c.path, None)
        if c.status in ("M", "D"):
            files.pop(c.path, None)
            src = base_source(engine.root, base, c.path)
            if src is not None:
                base_sources[c.path] = src
        if c.status == "R" and c.old_path:
            src = base_source(engine.root, base, c.old_path)
            if src is not None:
                base_sources[c.old_path] = src
    all_paths = frozenset([*files, *base_sources])
    out: list[ParsedFile] = []
    for path, pf in files.items():
        adapter = engine.registry.for_path(path)
        assert adapter is not None
        module = adapter.module_name(path, all_paths)
        out.append(pf if module == pf.module else dataclasses.replace(pf, module=module))
    parsed: dict[str, ParsedFile] = {}
    for path, src in sorted(base_sources.items()):
        adapter = engine.registry.for_path(path)
        if adapter is None:
            continue
        pf = engine.parser.parse(adapter, path, src, adapter.module_name(path, all_paths))
        parsed[path] = pf
        out.append(pf)
    return sorted(out, key=lambda f: f.path), parsed


def _similar(a: list[str], b: list[str]) -> float:
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


@dataclass
class DiffResult:
    diff: GraphDiff
    base_callers: dict[str, set[str]]
    changes: list[Change]


def graph_diff(engine: Engine, analysis: Analysis, since: str | None = None) -> DiffResult:
    base, changes = detect_changes(engine.root, since)
    changes = _relevant(engine, changes)
    changed_paths = {c.path for c in changes} | {c.old_path for c in changes if c.old_path}
    base_files, fresh_base = _base_files(engine, analysis.files, base, changes)

    index = SymbolIndex(base_files)
    by_adapter: dict[str, list[ParsedFile]] = {}
    for pf in base_files:
        found = engine.registry.for_path(pf.path)
        assert found is not None
        by_adapter.setdefault(found.name, []).append(pf)
    base_edges = []
    base_roots: list[str] = []
    for name, group in sorted(by_adapter.items()):
        adapter = engine.registry.get(name)
        edges = [e for e in adapter.resolve(group, index) if not e.external]
        base_edges.extend(edges)
        base_roots.extend(e.node for e in adapter.entries(group, index, engine.root, edges))
        base_roots.extend(adapter.library_roots(group, index))
    base_nodes = _nodes(base_files)
    bg = gr.build_graph(base_nodes, base_edges)
    base_isolated = set(gr.isolated_zones(bg, [r for r in base_roots if r in bg], gr.containment(base_nodes)))

    m = analysis.map
    cur = {n.id: n for n in m.nodes}
    old = {n.id: n for n in base_nodes}
    in_changed = {nid for nid, n in cur.items() if n.file in changed_paths}
    in_changed_old = {nid for nid, n in old.items() if n.file in changed_paths}
    added = sorted(n for n in in_changed if n not in old)
    removed = sorted(n for n in in_changed_old if n not in cur)
    changed = sorted(n for n in in_changed if n in old and old[n].body_hash != cur[n].body_hash)

    # Rename detection by body token similarity.
    renamed: dict[str, str] = {}
    if added and removed:
        tokens_new = _tokens_for(engine, analysis, {cur[n].file for n in added})
        tokens_old = {f"{pf.path}::{d.qualname}": d.tokens for pf in fresh_base.values() for d in pf.definitions}
        for r in removed:
            if old[r].kind == "module":
                continue
            best = None
            for a in added:
                if a in renamed.values() or cur[a].kind != old[r].kind:
                    continue
                score = _similar(tokens_old.get(r, []), tokens_new.get(a, []))
                if score >= RENAME_SIMILARITY and (best is None or score > best[0]):
                    best = (score, a)
            if best is not None:
                renamed[r] = best[1]
        added = [a for a in added if a not in renamed.values()]
        removed = [r for r in removed if r not in renamed]
    # A renamed function whose body also changed is both renamed and changed.

    def edge_set(edges: list[Edge], rename: dict[str, str]) -> dict[tuple[str, str], int]:
        out: dict[tuple[str, str], int] = {}
        for e in edges:
            if e.kind != "call" or e.dst is None or not e.resolved or e.inferred or e.src == e.dst:
                continue
            key = (rename.get(e.src, e.src), rename.get(e.dst, e.dst))
            out[key] = min(out.get(key, e.line), e.line)
        return out

    cur_edges = edge_set(analysis.edges, {})
    old_edges = edge_set(base_edges, renamed)
    added_edges = [EdgeRef(src=s, dst=d, line=ln) for (s, d), ln in sorted(cur_edges.items())
                   if (s, d) not in old_edges]
    removed_edges = [EdgeRef(src=s, dst=d, line=ln) for (s, d), ln in sorted(old_edges.items())
                     if (s, d) not in cur_edges]
    new_isolated = sorted(n for n in m.isolated if n in old and n not in base_isolated)

    module_only = [n for n in changed if cur[n].kind == "module"]
    changed = [n for n in changed if n not in module_only] + [
        n for n in module_only if any(e.src == n for e in added_edges + removed_edges)]

    base_callers: dict[str, set[str]] = {}
    for (s, d) in old_edges:
        base_callers.setdefault(d, set()).add(s)

    diff = GraphDiff(
        base=base or "",
        changed_files=sorted(changed_paths),
        added_nodes=added,
        removed_nodes=removed,
        changed_nodes=sorted(changed),
        renamed=renamed,
        added_edges=added_edges,
        removed_edges=removed_edges,
        new_isolated=new_isolated,
    )
    return DiffResult(diff=diff, base_callers=base_callers, changes=changes)


def _tokens_for(engine: Engine, analysis: Analysis, paths: set[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for pf in analysis.files:
        if pf.path not in paths:
            continue
        defs = pf.definitions
        if defs and not any(d.tokens for d in defs):
            adapter = engine.registry.for_path(pf.path)
            assert adapter is not None
            src = (engine.root / pf.path).read_bytes()
            defs = engine.parser.parse(adapter, pf.path, src, pf.module).definitions
        for d in defs:
            out[f"{pf.path}::{d.qualname}"] = d.tokens
    return out


def count_changed_functions(engine: Engine, since: str | None = None) -> dict[str, int]:
    """Fast change volume for the status bar: parses only changed files, at both revisions.
    Counts functions and methods whose body changed (added and removed ones included)."""
    base, changes = detect_changes(engine.root, since)
    changes = _relevant(engine, changes)
    total = 0
    files = 0
    for c in changes:
        adapter = engine.registry.for_path(c.path)
        if adapter is None:
            continue
        old_path = c.old_path or c.path
        before: dict[str, str] = {}
        after: dict[str, str] = {}
        if c.status != "A":
            src = base_source(engine.root, base, old_path)
            if src is not None:
                pf = engine.parse_source(adapter, old_path, src, "")
                before = {d.qualname: d.body_hash for d in pf.definitions if d.kind in ("function", "method")}
        if c.status != "D":
            try:
                src = (engine.root / c.path).read_bytes()
            except OSError:
                src = b""
            pf = engine.parse_source(adapter, c.path, src, "")
            after = {d.qualname: d.body_hash for d in pf.definitions if d.kind in ("function", "method")}
        n = sum(1 for q in after if before.get(q) != after[q]) + sum(1 for q in before if q not in after)
        if n:
            files += 1
            total += n
    return {"changedFunctions": total, "changedFiles": files}
