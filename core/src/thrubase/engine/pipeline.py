"""The public API that ties the steps together: ``build_map()`` and ``build_trail()``."""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .. import SCHEMA_VERSION, __version__
from ..adapters.base import Entry, LanguageAdapter, Registry, default_registry
from ..model import Edge, Map, Node, Repo, Stats, from_json, to_json
from ..store import Config, Store
from . import altitude as alt
from . import graph as gr
from .collect import collect
from .index import MODULE_QUALNAME, SymbolIndex, module_node_id, node_id
from .layout import layout
from .parse import ParsedFile, Parser, content_hash, normalize_source, parsed_from_json, parsed_to_json

ProgressFn = Callable[[str, int, int], None]
#: bumped whenever graph, altitude or layout output changes, invalidating cached maps
ENGINE_VERSION = "3"


class Cancelled(Exception):
    pass


class NoSupportedFiles(Exception):
    """Exit code 3 / JSON-RPC -32001."""


@dataclass
class CancelToken:
    _event: threading.Event = field(default_factory=threading.Event)

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def check(self) -> None:
        if self._event.is_set():
            raise Cancelled()


@dataclass
class Analysis:
    """Everything build_map produced, kept in memory for trails and diffs."""

    map: Map
    files: list[ParsedFile]
    index: SymbolIndex
    edges: list[Edge]
    graph: object
    root: Path


def _noop(stage: str, done: int, total: int) -> None:
    pass


class Engine:
    """One engine per repository root. Holds the parse cache across calls."""

    def __init__(self, root: Path, store: Store | None = None, config: Config | None = None,
                 registry: Registry | None = None) -> None:
        self.root = root.resolve()
        self.store = store or Store()
        self.config = config or self.store.load_config()
        self.registry = registry or default_registry()
        self.parser = Parser()
        self._parsed: dict[str, ParsedFile] = {}  # "<adapter version>:<content hash>:<module>" -> file
        self._analysis: Analysis | None = None
        self._loaded_disk_cache = False

    # ------------------------------------------------------------------ parse cache
    def _cache_key(self, adapter: LanguageAdapter, digest: str, path: str, module: str) -> str:
        return f"{adapter.version}:{digest}:{path}:{module}"

    def _load_disk_cache(self) -> None:
        if self._loaded_disk_cache:
            return
        self._loaded_disk_cache = True
        data = self.store.read_json(self.store.parsed_path(self.root))
        if isinstance(data, dict) and data.get("schema") == SCHEMA_VERSION:
            for key, value in data.get("files", {}).items():
                try:
                    self._parsed[key] = parsed_from_json(value)
                except (KeyError, TypeError):
                    continue

    def _save_disk_cache(self, keys: list[str]) -> None:
        files = {k: parsed_to_json(self._parsed[k]) for k in keys if k in self._parsed}
        self.store.write_json(self.store.parsed_path(self.root), {"schema": SCHEMA_VERSION, "files": files})

    def parse_source(self, adapter: LanguageAdapter, path: str, source: bytes, module: str) -> ParsedFile:
        digest = content_hash(source)
        key = self._cache_key(adapter, digest, path, module)
        cached = self._parsed.get(key)
        if cached is not None:
            return cached
        pf = self.parser.parse(adapter, path, source, module)
        self._parsed[key] = pf
        return pf

    # ------------------------------------------------------------------ map
    def snapshot(self, digests: list[tuple[str, str]]) -> str:
        h = hashlib.sha256()
        h.update(f"schema={SCHEMA_VERSION};v={__version__};e={ENGINE_VERSION};".encode())
        for a in self.registry:
            h.update(f"{a.name}={a.version};".encode())
        w = self.config.weights
        h.update(f"w={w['alpha']},{w['beta']},{w['gamma']};s={self.config.summits};".encode())
        for path, digest in digests:
            h.update(f"{path}\0{digest}\n".encode())
        return h.hexdigest()[:16]

    def build_map(self, *, no_cache: bool = False, on_progress: ProgressFn = _noop,
                  cancel: CancelToken | None = None) -> Map:
        return self.analyze(no_cache=no_cache, on_progress=on_progress, cancel=cancel).map

    def analyze(self, *, no_cache: bool = False, on_progress: ProgressFn = _noop,
                cancel: CancelToken | None = None) -> Analysis:
        started = time.perf_counter()
        cancel = cancel or CancelToken()
        cfg = self.config
        on_progress("collect", 0, 1)
        collected = collect(self.root, self.registry, max_files=cfg.max_files, extra_excludes=cfg.extra_excludes)
        if not collected.files:
            raise NoSupportedFiles(str(self.root))
        on_progress("collect", 1, 1)
        cancel.check()

        sources: dict[str, bytes] = {}
        digests: list[tuple[str, str]] = []
        total = len(collected.files)
        for i, (path, _) in enumerate(collected.files):
            try:
                data = normalize_source((self.root / path).read_bytes())
            except OSError:
                data = b""
            sources[path] = data
            digests.append((path, content_hash(data)))
            if i % 200 == 0:
                cancel.check()
        snapshot = self.snapshot(digests)

        if self._analysis is not None and self._analysis.map.repo.snapshot == snapshot and not no_cache:
            return self._analysis

        if not no_cache:
            self._load_disk_cache()

        all_paths = frozenset(collected.paths)
        files: list[ParsedFile] = []
        adapters_of: dict[str, LanguageAdapter] = {}
        keys: list[str] = []
        for i, (path, adapter) in enumerate(collected.files):
            module = adapter.module_name(path, all_paths)
            pf = self.parse_source(adapter, path, sources[path], module)
            keys.append(self._cache_key(adapter, pf.content_hash, path, module))
            files.append(pf)
            adapters_of[path] = adapter
            if i % 25 == 0 or i == total - 1:
                on_progress("parse", i + 1, total)
                cancel.check()

        cached_map = None if no_cache else self.store.load_map(self.root, snapshot)
        m_cached: Map | None = None
        if cached_map is not None and cached_map.get("schema_version") == SCHEMA_VERSION:
            try:
                m_cached = from_json(Map, cached_map)
            except (KeyError, TypeError, ValueError):
                m_cached = None
        if m_cached is not None:
            m = m_cached
            index = SymbolIndex(files)
            edges = m.edges
            g = gr.build_graph(m.nodes, edges)
            self._analysis = Analysis(map=m, files=files, index=index, edges=edges, graph=g, root=self.root)
            on_progress("done", 1, 1)
            return self._analysis

        on_progress("resolve", 0, 1)
        index = SymbolIndex(files)
        edges: list[Edge] = []
        entries: list[Entry] = []
        by_adapter: dict[str, list[ParsedFile]] = {}
        for pf in files:
            by_adapter.setdefault(adapters_of[pf.path].name, []).append(pf)
        for name, group in sorted(by_adapter.items()):
            adapter = self.registry.get(name)
            edges.extend(adapter.resolve(group, index))
        cancel.check()
        on_progress("resolve", 1, 1)

        nodes = _nodes(files)
        external = sum(1 for e in edges if e.external)
        calls = [e for e in edges if e.kind == "call" and not e.external]
        resolved = sum(1 for e in calls if e.resolved)
        edges = [e for e in edges if not e.external]
        roots: list[str] = []
        for name, group in sorted(by_adapter.items()):
            adapter = self.registry.get(name)
            entries.extend(adapter.entries(group, index, self.root, edges))
            roots.extend(adapter.library_roots(group, index))

        on_progress("graph", 0, 1)
        g = gr.build_graph(nodes, edges)
        members = gr.containment(nodes)
        entry_ids = [e.node for e in entries if e.node in g]
        library = [r for r in roots if r in g and r not in entry_ids]
        isolated = gr.isolated_zones(g, entry_ids + library, members)
        loc = {n.id: n.loc for n in nodes}
        h = alt.altitude(g, loc, cfg.weights, skip={n.id for n in nodes if n.kind == "module"})
        for n in nodes:
            n.h = h.get(n.id, 0.0)
        isolated_set = set(isolated)
        callables = [n for n in nodes if n.kind in gr.CALLABLE and n.id not in isolated_set]
        summits = [n.id for n in sorted(callables, key=lambda n: (-n.h, n.id))[: max(cfg.summits, 1)]]
        entry_kind = {e.node: e.kind for e in entries}
        for n in nodes:
            if n.id in entry_kind:
                n.role = "entry"
                n.entry_kind = entry_kind[n.id]
            elif n.id in summits:
                n.role = "summit"
            elif n.id in isolated_set:
                n.role = "isolated"
        on_progress("graph", 1, 1)
        cancel.check()

        on_progress("layout", 0, 1)
        coords = layout(nodes, edges)
        for n in nodes:
            n.x, n.y = coords.get(n.id, (0.5, 0.5))
        on_progress("layout", 1, 1)

        rate = round(resolved / len(calls), 4) if calls else 1.0
        stats = Stats(files=len(files), skipped_files=collected.skipped,
                      parse_errors=sum(1 for f in files if f.errors), calls=len(calls) + external,
                      external_calls=external, resolved_calls=resolved, resolution_rate=rate,
                      seconds=round(time.perf_counter() - started, 3))
        repo = Repo(root=self.root.as_posix(), name=self.root.name, snapshot=snapshot, files=len(files),
                    skipped=collected.skipped, languages=sorted(by_adapter))
        m = Map(repo=repo, nodes=nodes, edges=edges, entries=entry_ids, summits=summits, isolated=isolated,
                stats=stats, weights=dict(cfg.weights), library=library)
        self.store.save_map(self.root, snapshot, to_json(m))
        self._save_disk_cache(keys)
        self._analysis = Analysis(map=m, files=files, index=index, edges=edges, graph=g, root=self.root)
        on_progress("done", 1, 1)
        return self._analysis


def _nodes(files: list[ParsedFile]) -> list[Node]:
    out: list[Node] = []
    for pf in sorted(files, key=lambda f: f.path):
        out.append(Node(id=module_node_id(pf.path), kind="module", name=pf.module.rsplit(".", 1)[-1] or pf.path,
                        qualname=MODULE_QUALNAME, file=pf.path, start_line=1, end_line=max(pf.line_count, 1),
                        loc=pf.line_count, body_hash=str(pf.extra.get("module_hash", ""))))
        for d in pf.definitions:
            out.append(Node(id=node_id(pf.path, d.qualname), kind=d.kind, name=d.name, qualname=d.qualname,
                            file=pf.path, start_line=d.start_line, end_line=d.end_line,
                            loc=d.end_line - d.start_line + 1, body_hash=d.body_hash))
    return out


def build_map(root: Path | str, *, store: Store | None = None, config: Config | None = None,
              no_cache: bool = False, on_progress: ProgressFn = _noop) -> Map:
    return Engine(Path(root), store=store, config=config).build_map(no_cache=no_cache, on_progress=on_progress)
