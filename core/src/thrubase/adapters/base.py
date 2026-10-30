"""The ``LanguageAdapter`` protocol and the registry that finds adapters by file extension.

Everything language-specific lives behind this protocol, so adding a language means adding
an ``adapters/<language>/`` package and registering it; ``engine/`` never changes.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import tree_sitter as ts

    from ..engine.index import SymbolIndex
    from ..engine.parse import ParsedFile
    from ..model import Edge


@dataclass
class Entry:
    node: str
    kind: str
    detail: str = ""


@runtime_checkable
class LanguageAdapter(Protocol):
    name: str
    #: bumped whenever extraction or resolution output changes, invalidating caches
    version: str
    extensions: tuple[str, ...]
    #: gitignore-style patterns that are never analyzed (virtualenvs, build output, tests …)
    excludes: tuple[str, ...]

    def language(self) -> ts.Language: ...

    def query_source(self) -> str: ...

    def module_name(self, path: str, all_paths: frozenset[str]) -> str: ...

    def extract(self, pf: ParsedFile, tree: ts.Tree, matches: list[tuple[int, dict[str, list[ts.Node]]]],
                source: bytes) -> None: ...

    def resolve(self, files: list[ParsedFile], index: SymbolIndex) -> list[Edge]: ...

    def entries(self, files: list[ParsedFile], index: SymbolIndex, root: Path,
                edges: list[Edge]) -> list[Entry]: ...

    def library_roots(self, files: list[ParsedFile], index: SymbolIndex) -> list[str]:
        """Node ids a library exposes as its API (reached even if no entry point calls them)."""
        ...


class Registry:
    def __init__(self) -> None:
        self._adapters: list[LanguageAdapter] = []

    def register(self, adapter: LanguageAdapter) -> None:
        if any(a.name == adapter.name for a in self._adapters):
            self._adapters = [a for a in self._adapters if a.name != adapter.name]
        self._adapters.append(adapter)

    def unregister(self, name: str) -> None:
        self._adapters = [a for a in self._adapters if a.name != name]

    def for_path(self, path: str) -> LanguageAdapter | None:
        lower = path.lower()
        for a in self._adapters:
            if lower.endswith(a.extensions):
                return a
        return None

    def get(self, name: str) -> LanguageAdapter:
        for a in self._adapters:
            if a.name == name:
                return a
        raise KeyError(name)

    def __iter__(self) -> Iterator[LanguageAdapter]:
        return iter(list(self._adapters))

    @property
    def names(self) -> list[str]:
        return [a.name for a in self._adapters]

    def describe(self) -> list[dict[str, Any]]:
        return [{"name": a.name, "extensions": list(a.extensions)} for a in self._adapters]


registry = Registry()


def default_registry() -> Registry:
    if not registry.names:
        from .python import PythonAdapter

        registry.register(PythonAdapter())
    return registry
