"""PythonAdapter: everything Python-specific about Thrubase."""

from __future__ import annotations

import hashlib
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

import tree_sitter as ts
import tree_sitter_python as tsp

from ...engine.parse import Call, Definition, Import, ParsedFile, Spot
from ..base import Entry

if TYPE_CHECKING:
    from ...engine.index import SymbolIndex
    from ...model import Edge

_DEF_TYPES = ("function_definition", "class_definition")
_HASH_SKIP = frozenset({"comment"})


def _text(node: ts.Node | None) -> str:
    if node is None or node.text is None:
        return ""
    return node.text.decode("utf-8", "replace")


def _compact(text: str) -> str:
    return "".join(text.split())


def _line(node: ts.Node) -> int:
    return node.start_point[0] + 1


def _end_line(node: ts.Node) -> int:
    row, col = node.end_point
    # A node ending at column 0 really ended on the previous line's newline.
    return row if col == 0 and row > node.start_point[0] else row + 1


_OPTIONAL = ("Optional", "typing.Optional", "t.Optional", "Final", "typing.Final", "ClassVar",
             "typing.ClassVar", "Annotated", "typing.Annotated", "type", "Type", "typing.Type")


def _type_name(node: ts.Node | None) -> str:
    """The class named by an annotation: ``Foo``, ``m.Foo``, ``"Foo"``, ``Foo | None``,
    ``Optional[Foo]``. Containers (``list[Foo]``) and unions of classes give ``""``."""
    if node is None:
        return ""
    if node.type == "type" and node.named_children:
        return _type_name(node.named_children[0])
    if node.type in ("identifier", "attribute"):
        return _compact(_text(node))
    if node.type == "string":
        inner = _text(node).strip("\"'")
        return inner if inner.replace(".", "").replace("_", "").isalnum() else ""
    if node.type == "binary_operator":  # X | None
        parts = [c for c in node.named_children if _text(c) != "None"]
        return _type_name(parts[0]) if len(parts) == 1 else ""
    if node.type in ("generic_type", "subscript"):
        head = node.named_children[0] if node.named_children else None
        if head is not None and _compact(_text(head)) in _OPTIONAL:
            args = [c for c in node.named_children[1:]]
            flat: list[ts.Node] = []
            for a in args:
                flat.extend(a.named_children if a.type in ("type_parameter", "subscript") else [a])
            flat = [a for a in flat if _text(a) != "None"]
            return _type_name(flat[0]) if flat else ""
    return ""


def _enclosing_def(node: ts.Node) -> ts.Node | None:
    p = node.parent
    while p is not None:
        if p.type in _DEF_TYPES:
            return p
        p = p.parent
    return None


_LITERALS = frozenset({"string", "concatenated_string", "list", "dictionary", "set", "tuple", "integer",
                       "float", "list_comprehension", "dictionary_comprehension", "set_comprehension",
                       "generator_expression", "true", "false", "none", "parenthesized_expression"})
_IMPORTS = frozenset({"import_statement", "import_from_statement", "future_import_statement"})


def _tokens(node: ts.Node, skip_nested: bool = True, skip: frozenset[str] = frozenset()) -> list[str]:
    """Leaf tokens of a definition, without comments and without nested definitions."""
    out: list[str] = []
    stack = [node]
    root = node
    while stack:
        n = stack.pop()
        if n.type in _HASH_SKIP or n.type in skip:
            continue
        if skip_nested and n is not root and n.type in _DEF_TYPES:
            continue
        if n.type == "decorated_definition" and skip_nested and n is not root:
            continue
        if n.child_count == 0 or n.type == "string":
            out.append(_text(n))
            continue
        stack.extend(reversed(n.children))
    return out


class PythonAdapter:
    name = "python"
    version = "py-4"
    extensions = (".py",)
    excludes = (
        ".git/",
        ".hg/",
        ".venv/",
        "venv/",
        "env/",
        ".env/",
        ".tox/",
        ".nox/",
        "__pycache__/",
        "site-packages/",
        "node_modules/",
        "build/",
        "dist/",
        ".eggs/",
        "*.egg-info/",
        ".mypy_cache/",
        ".pytest_cache/",
        "tests/",
        "test/",
        "testing/",
        "test_*.py",
        "*_test.py",
        "conftest.py",
        "docs/",
        "examples/",
        "migrations/",
        "setup.py",
        "noxfile.py",
    )

    def __init__(self) -> None:
        self._lang: ts.Language | None = None

    # -------------------------------------------------------------- grammar
    def language(self) -> ts.Language:
        if self._lang is None:
            self._lang = ts.Language(tsp.language())
        return self._lang

    def query_source(self) -> str:
        return resources.files(__package__).joinpath("queries.scm").read_text(encoding="utf-8")

    # -------------------------------------------------------------- modules
    def module_name(self, path: str, all_paths: frozenset[str]) -> str:
        """Dotted module name. Walks up while parent folders are packages (have ``__init__.py``);
        a leading ``src/`` layout folder is never part of the name."""
        parts = path.split("/")
        stem = parts[-1][: -len(".py")]
        dirs = parts[:-1]
        mod = [] if stem == "__init__" else [stem]
        i = len(dirs)
        while i > 0:
            pkg_init = "/".join([*dirs[:i], "__init__.py"])
            if pkg_init not in all_paths:
                break
            i -= 1
        names = dirs[i:] + mod
        if not names:
            names = dirs[-1:] if dirs else [stem]
        return ".".join(names)

    # -------------------------------------------------------------- extraction
    def extract(self, pf: ParsedFile, tree: ts.Tree,
                matches: list[tuple[int, dict[str, list[ts.Node]]]], source: bytes) -> None:
        qual_of: dict[int, str] = {}

        def qualname(def_node: ts.Node) -> str:
            if def_node.id in qual_of:
                return qual_of[def_node.id]
            parts = [_text(def_node.child_by_field_name("name"))]
            p = _enclosing_def(def_node)
            if p is not None:
                q = f"{qualname(p)}.{parts[0]}"
            else:
                q = parts[0]
            qual_of[def_node.id] = q
            return q

        def scope_of(node: ts.Node) -> str | None:
            d = _enclosing_def(node)
            return qualname(d) if d is not None else None

        def function_scope_of(node: ts.Node) -> str | None:
            d = _enclosing_def(node)
            while d is not None and d.type != "function_definition":
                d = _enclosing_def(d)
            return qualname(d) if d is not None else None

        seen_defs: set[str] = set()
        defs_by_node: dict[int, int] = {}
        # Imports are left out so files where only import lines changed do not count as changed.
        module_tokens: list[str] = _tokens(tree.root_node, skip=_IMPORTS)
        pf.extra["module_hash"] = hashlib.sha1(" ".join(module_tokens).encode()).hexdigest()[:16]

        for _, caps in matches:
            if "def.function" in caps or "def.class" in caps:
                is_fn = "def.function" in caps
                node = caps["def.function" if is_fn else "def.class"][0]
                q = qualname(node)
                if q in seen_defs:  # redefinition (e.g. property setter): keep the first
                    q_alt = f"{q}@{_line(node)}"
                    qual_of[node.id] = q_alt
                    q = q_alt
                seen_defs.add(q)
                parent_node = _enclosing_def(node)
                parent = qualname(parent_node) if parent_node is not None else None
                if is_fn:
                    kind = "method" if parent_node is not None and parent_node.type == "class_definition" \
                        else "function"
                else:
                    kind = "class"
                decorators: list[str] = []
                if node.parent is not None and node.parent.type == "decorated_definition":
                    for ch in node.parent.children:
                        if ch.type == "decorator":
                            decorators.append(_compact(_text(ch))[1:])
                bases: list[str] = []
                if "def.bases" in caps:
                    for arg in caps["def.bases"][0].named_children:
                        if arg.type in ("identifier", "attribute"):
                            bases.append(_compact(_text(arg)))
                toks = _tokens(node)
                name = _text(node.child_by_field_name("name"))
                body_toks = [t for t in toks if t != name]
                params: dict[str, str] = {}
                if "def.params" in caps:
                    for prm in caps["def.params"][0].named_children:
                        if prm.type in ("typed_parameter", "typed_default_parameter"):
                            pname = prm.child_by_field_name("name")
                            if pname is None:
                                pname = next((c for c in prm.named_children if c.type == "identifier"), None)
                            ptype = _type_name(prm.child_by_field_name("type"))
                            if pname is not None and ptype:
                                params[_text(pname)] = ptype
                returns = _type_name(caps["def.returns"][0]) if "def.returns" in caps else ""
                defs_by_node[node.id] = len(pf.definitions)
                pf.definitions.append(Definition(
                    qualname=q, name=name, kind=kind,  # type: ignore[arg-type]
                    start_line=_line(node), end_line=_end_line(node), parent=parent,
                    bases=bases, decorators=decorators,
                    body_hash=hashlib.sha1(" ".join(toks).encode()).hexdigest()[:16],
                    tokens=body_toks,
                    is_async=any(c.type == "async" for c in node.children),
                    params=params, returns=returns,
                ))
            elif "bind" in caps:
                left = caps["bind.left"][0]
                value = ""
                if "bind.type" in caps:
                    tname = _type_name(caps["bind.type"][0])
                    value = f"ann:{tname}" if tname else ""
                if not value and "bind.right" in caps:
                    right = caps["bind.right"][0]
                    if right.type == "call":
                        fn = right.child_by_field_name("function")
                        if fn is not None and fn.type in ("identifier", "attribute"):
                            value = "call:" + _compact(_text(fn))
                    elif right.type == "await":
                        inner = right.named_children[0] if right.named_children else None
                        if inner is not None and inner.type == "call":
                            fn = inner.child_by_field_name("function")
                            if fn is not None and fn.type in ("identifier", "attribute"):
                                value = "call:" + _compact(_text(fn))
                if not value:
                    continue
                owner = _enclosing_def(caps["bind"][0])
                if owner is None or owner.id not in defs_by_node:
                    continue
                d_owner = pf.definitions[defs_by_node[owner.id]]
                if left.type == "identifier":
                    target = d_owner.attrs if d_owner.kind == "class" else d_owner.locals
                    target.setdefault(_text(left), value)
                elif left.type == "attribute" and d_owner.kind == "method":
                    obj = left.child_by_field_name("object")
                    if obj is not None and _text(obj) == "self":
                        cls_node = _enclosing_def(owner)
                        if cls_node is not None and cls_node.id in defs_by_node:
                            attr_name = _text(left.child_by_field_name("attribute"))
                            pf.definitions[defs_by_node[cls_node.id]].attrs.setdefault(attr_name, value)
            elif "import" in caps:
                node = caps["import"][0]
                scope = function_scope_of(node)
                for ch in node.named_children:
                    if ch.type == "dotted_name":
                        pf.imports.append(Import(module=_text(ch), names=[], level=0, line=_line(node),
                                                 scope=scope))
                    elif ch.type == "aliased_import":
                        pf.imports.append(Import(
                            module=_text(ch.child_by_field_name("name")), names=[], level=0,
                            line=_line(node), scope=scope, alias=_text(ch.child_by_field_name("alias"))))
            elif "import.from" in caps:
                node = caps["import.from"][0]
                scope = function_scope_of(node)
                mod_node = node.child_by_field_name("module_name")
                level = 0
                module = ""
                if mod_node is not None:
                    if mod_node.type == "relative_import":
                        for ch in mod_node.children:
                            if ch.type == "import_prefix":
                                level = _text(ch).count(".")
                            elif ch.type == "dotted_name":
                                module = _text(ch)
                    else:
                        module = _text(mod_node)
                names: list[tuple[str, str | None]] = []
                for ch in node.children_by_field_name("name"):
                    if ch.type == "dotted_name":
                        names.append((_text(ch), None))
                    elif ch.type == "aliased_import":
                        names.append((_text(ch.child_by_field_name("name")),
                                      _text(ch.child_by_field_name("alias"))))
                if any(ch.type == "wildcard_import" for ch in node.children):
                    names.append(("*", None))
                pf.imports.append(Import(module=module, names=names, level=level, line=_line(node),
                                         scope=scope, is_from=True))
            elif "call" in caps:
                node = caps["call"][0]
                callee_node = caps["call.callee"][0]
                callee = _compact(_text(callee_node))
                if callee_node.type not in ("identifier", "attribute"):
                    # Keep `super().m` and `super(C, self).m`; everything else is a dynamic target.
                    callee = callee if callee.startswith("super(") else f"<expr>{callee[:40]}"
                elif callee_node.type == "attribute":
                    obj = callee_node.child_by_field_name("object")
                    if obj is not None and obj.type == "call":
                        inner = _compact(_text(obj.child_by_field_name("function")))
                        attr = _text(callee_node.child_by_field_name("attribute"))
                        callee = f"super().{attr}" if inner == "super" else f"<expr>{callee[:40]}"
                    elif obj is not None and obj.type in _LITERALS:
                        callee = f"<lit>{callee[:40]}"
                    elif obj is not None and obj.type not in ("identifier", "attribute"):
                        callee = f"<expr>{callee[:40]}"
                caller = scope_of(node)
                pf.calls.append(Call(caller=caller, callee=callee, line=_line(node),
                                     end_line=_end_line(node), col=node.start_point[1]))
                for arg in caps["call.args"][0].named_children:
                    if arg.type == "keyword_argument":
                        arg = arg.child_by_field_name("value") or arg
                    if arg.type in ("identifier", "attribute"):
                        pf.refs.append(Call(caller=caller, callee=_compact(_text(arg)), line=_line(arg),
                                            end_line=_line(arg), col=arg.start_point[1]))
            elif "spot.raise" in caps or "spot.except" in caps or "spot.return" in caps:
                kind = next(k for k in ("spot.raise", "spot.except", "spot.return") if k in caps)
                node = caps[kind][0]
                end = _end_line(node)
                if kind == "spot.except":
                    # The handler header is the "spot"; its body belongs to it as well.
                    block = next((c for c in node.children if c.type == "block"), None)
                    end = _end_line(block) if block is not None else end
                pf.spots.append(Spot(kind=kind.split(".")[1], owner=function_scope_of(node),
                                     start_line=_line(node), end_line=end,
                                     detail=_compact(_text(node))[:60]))
            elif "main.block" in caps:
                cond = _compact(_text(caps["main.cond"][0]))
                if cond in ('__name__=="__main__"', "__name__=='__main__'",
                            '"__main__"==__name__', "'__main__'==__name__"):
                    node = caps["main.block"][0]
                    pf.extra["main_block"] = [_line(node), _end_line(node)]
            elif "assign.name" in caps:
                name = _text(caps["assign.name"][0])
                value = caps["assign.value"][0]
                if value.type == "call":
                    fn = value.child_by_field_name("function")
                    if fn is not None and fn.type in ("identifier", "attribute"):
                        pf.assignments[name] = "call:" + _compact(_text(fn))
                elif value.type in ("identifier", "attribute"):
                    pf.assignments[name] = "ref:" + _compact(_text(value))
                if name == "urlpatterns" and value.type in ("list", "binary_operator"):
                    pf.extra["urlpatterns"] = _url_refs(value)

        pf.definitions.sort(key=lambda d: (d.start_line, d.qualname))
        pf.calls.sort(key=lambda c: (c.line, c.col))
        pf.refs.sort(key=lambda c: (c.line, c.col))
        pf.spots.sort(key=lambda s: s.start_line)

    # -------------------------------------------------------------- resolution / entries
    def resolve(self, files: list[ParsedFile], index: SymbolIndex) -> list[Edge]:
        from .resolve import Resolver

        return Resolver(files, index).edges()

    def entries(self, files: list[ParsedFile], index: SymbolIndex, root: Path,
                edges: list[Edge]) -> list[Entry]:
        from .entry import detect_entries

        return detect_entries(files, index, root, edges)

    def library_roots(self, files: list[ParsedFile], index: SymbolIndex) -> list[str]:
        from .resolve import Resolver

        return Resolver(files, index).library_roots()


def _url_refs(value: ts.Node) -> list[list[object]]:
    """Second positional argument of each ``path()``/``re_path()``/``url()`` call in urlpatterns."""
    refs: list[list[object]] = []
    stack = [value]
    while stack:
        n = stack.pop()
        if n.type == "call":
            fn = _compact(_text(n.child_by_field_name("function")))
            if fn.split(".")[-1] in ("path", "re_path", "url"):
                args = [a for a in (n.child_by_field_name("arguments") or n).named_children
                        if a.type != "keyword_argument" and a.type != "comment"]
                if len(args) >= 2:
                    view = args[1]
                    if view.type == "call":  # Class.as_view()
                        f = view.child_by_field_name("function")
                        txt = _compact(_text(f))
                        if txt.endswith(".as_view"):
                            refs.append([txt[: -len(".as_view")], _line(view)])
                        continue
                    if view.type in ("identifier", "attribute"):
                        refs.append([_compact(_text(view)), _line(view)])
                        continue
        stack.extend(reversed(n.named_children))
    return refs


__all__ = ["Entry", "PythonAdapter"]
