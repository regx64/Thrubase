"""tree-sitter parsing into a language-independent ``ParsedFile``.

The engine owns the parser and the query cursor; an adapter supplies the grammar, the
query source and ``extract``, which turns query captures into definitions, imports,
calls and "meaningful spots". Files with syntax errors are still parsed: tree-sitter
recovers, and whatever it could build is extracted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import tree_sitter as ts

from ..model import NodeKind

if TYPE_CHECKING:
    from ..adapters.base import LanguageAdapter


@dataclass
class Definition:
    qualname: str
    name: str
    kind: NodeKind
    start_line: int
    end_line: int
    parent: str | None = None
    bases: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    body_hash: str = ""
    is_async: bool = False
    #: parameter name -> annotation text (functions)
    params: dict[str, str] = field(default_factory=dict)
    #: local name -> "call:<callee>" or "ann:<type>" (functions)
    locals: dict[str, str] = field(default_factory=dict)
    #: attribute name -> "call:<callee>" or "ann:<type>" (classes: class body and ``self.x = …``)
    attrs: dict[str, str] = field(default_factory=dict)
    #: return annotation text (functions)
    returns: str = ""


@dataclass
class Import:
    module: str
    names: list[tuple[str, str | None]]
    level: int
    line: int
    scope: str | None = None
    #: ``import a.b as c`` style (module import) vs ``from a import b``
    is_from: bool = False
    alias: str | None = None


@dataclass
class Call:
    caller: str | None
    callee: str
    line: int
    end_line: int
    col: int = 0


@dataclass
class Spot:
    """A place in a definition worth asking about (locate checkpoints)."""

    kind: str  # call | raise | except | return
    owner: str | None
    start_line: int
    end_line: int
    detail: str = ""


@dataclass
class ParsedFile:
    path: str
    module: str
    content_hash: str
    line_count: int
    definitions: list[Definition] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    #: functions passed as values (``router.add("/", handler)``): reachability, not calls
    refs: list[Call] = field(default_factory=list)
    spots: list[Spot] = field(default_factory=list)
    #: module-level name -> attribute chain it was assigned from (``app = Flask(...)``)
    assignments: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    errors: int = 0


def normalize_source(source: bytes) -> bytes:
    """CRLF and CR become LF so line numbers and hashes match across platforms."""
    if b"\r" in source:
        source = source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return source


def content_hash(source: bytes) -> str:
    return hashlib.sha256(normalize_source(source)).hexdigest()[:20]


class Parser:
    """Caches one tree-sitter parser and compiled query per adapter."""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[ts.Parser, ts.Query]] = {}
        self.count = 0  # number of files parsed, used by tests

    def _get(self, adapter: LanguageAdapter) -> tuple[ts.Parser, ts.Query]:
        if adapter.name not in self._cache:
            lang = adapter.language()
            self._cache[adapter.name] = (ts.Parser(lang), ts.Query(lang, adapter.query_source()))
        return self._cache[adapter.name]

    def parse(self, adapter: LanguageAdapter, path: str, source: bytes, module: str) -> ParsedFile:
        source = normalize_source(source)
        parser, query = self._get(adapter)
        tree = parser.parse(source)
        self.count += 1
        cursor = ts.QueryCursor(query)
        matches = cursor.matches(tree.root_node)
        pf = ParsedFile(
            path=path,
            module=module,
            content_hash=hashlib.sha256(source).hexdigest()[:20],
            line_count=source.count(b"\n") + (0 if source.endswith(b"\n") or not source else 1),
        )
        adapter.extract(pf, tree, matches, source)
        pf.errors = _count_errors(tree.root_node)
        return pf


def _count_errors(root: ts.Node) -> int:
    if not root.has_error:
        return 0
    count = 0
    stack = [root]
    while stack:
        n = stack.pop()
        if n.is_error or n.is_missing:
            count += 1
            continue
        if n.has_error:
            stack.extend(n.children)
    return max(count, 1)


def parsed_to_json(pf: ParsedFile) -> dict[str, Any]:
    """Plain JSON for the on-disk parse cache (``dataclasses.asdict`` is far slower)."""
    return {
        "path": pf.path, "module": pf.module, "content_hash": pf.content_hash, "line_count": pf.line_count,
        "definitions": [dict(d.__dict__) for d in pf.definitions],
        "imports": [dict(i.__dict__) for i in pf.imports],
        "calls": [dict(c.__dict__) for c in pf.calls],
        "refs": [dict(c.__dict__) for c in pf.refs],
        "spots": [dict(s.__dict__) for s in pf.spots],
        "assignments": pf.assignments, "extra": pf.extra, "errors": pf.errors,
    }


def parsed_from_json(d: dict[str, Any]) -> ParsedFile:
    return ParsedFile(
        path=d["path"], module=d["module"], content_hash=d["content_hash"], line_count=d["line_count"],
        definitions=[Definition(**x) for x in d["definitions"]],
        imports=[Import(**{**x, "names": [tuple(n) for n in x["names"]]}) for x in d["imports"]],
        calls=[Call(**x) for x in d["calls"]],
        refs=[Call(**x) for x in d.get("refs", [])],
        spots=[Spot(**x) for x in d["spots"]],
        assignments=d.get("assignments", {}), extra=d.get("extra", {}), errors=d.get("errors", 0),
    )
