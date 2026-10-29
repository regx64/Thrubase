"""Python name resolution.

Handles absolute and relative imports, ``from x import y as z``, re-exports through
``__init__``, ``self.m()``/``cls.m()``, ``super().m()``, attribute chains through modules
and classes, the inheritance chain (a simple left-to-right MRO), constructor calls
(``C()`` → ``C.__init__``) and instances assigned at module level (``app = Flask()``).

Anything that cannot be determined statically becomes an edge with ``resolved=False``.
Calls into the standard library, dependencies or builtins are ``external``.
"""

from __future__ import annotations

import builtins
from dataclasses import dataclass

from ...engine.index import SymbolIndex, module_node_id, node_id
from ...engine.parse import Import, ParsedFile
from ...model import Edge

_BUILTINS = frozenset(dir(builtins))

# Method names too generic to infer a target from, even when one definition in the repo has them.
_GENERIC = frozenset(
    {n for t in (dict, list, str, set, bytes, object, int, tuple, frozenset) for n in dir(t)}
    | {
        "read", "write", "close", "open", "run", "start", "stop", "send", "recv", "info", "debug",
        "warning", "warn", "error", "exception", "critical", "log", "format", "get", "set", "post",
        "put", "delete", "patch", "head", "options", "call", "apply", "load", "loads", "dump",
        "dumps", "save", "flush", "reset", "clear", "next", "iter", "wait", "result", "submit",
        "connect", "execute", "commit", "rollback", "fetch", "fetchone", "fetchall", "match",
        "search", "sub", "group", "groups", "emit", "handle", "process", "render", "parse", "build",
        "validate", "init", "setup", "teardown", "main", "name", "value", "keys", "items", "values",
    }
)


@dataclass(frozen=True)
class Target:
    kind: str  # module | node | instance | external
    ref: str


EXTERNAL = Target("external", "")


class Resolver:
    def __init__(self, files: list[ParsedFile], index: SymbolIndex) -> None:
        self.files = sorted(files, key=lambda f: f.path)
        self.index = index
        self._mods = set(index.modules)
        self._mod_prefixes = {m.rsplit(".", i)[0] for m in self._mods for i in range(m.count(".") + 1)}
        self._mro: dict[str, tuple[list[str], bool]] = {}
        self._imports: dict[tuple[str, str | None], dict[str, tuple[Import, str | None]]] = {}
        self._stars: dict[str, list[Import]] = {}
        self._scope_defs: dict[tuple[str, str | None], dict[str, str]] = {}
        self._kinds: dict[str, str] = {}
        for f in self.files:
            for imp in f.imports:
                table = self._imports.setdefault((f.path, imp.scope), {})
                if imp.is_from:
                    for name, alias in imp.names:
                        if name == "*":
                            self._stars.setdefault(f.path, []).append(imp)
                        else:
                            table[alias or name] = (imp, name)
                elif imp.alias:
                    table[imp.alias] = (imp, None)
                else:
                    table.setdefault(imp.module.split(".")[0], (imp, None))
            for d in f.definitions:
                nid = node_id(f.path, d.qualname)
                self._kinds[nid] = d.kind
                self._scope_defs.setdefault((f.path, d.parent), {}).setdefault(d.name, nid)
        self._file_by_path = {f.path: f for f in self.files}

    # ------------------------------------------------------------------ modules
    def _module_exists(self, dotted: str) -> bool:
        return dotted in self._mod_prefixes

    def _relative_base(self, pf: ParsedFile, imp: Import) -> str:
        if imp.level == 0:
            return imp.module
        parts = pf.module.split(".") if pf.module else []
        is_pkg = pf.path.endswith("__init__.py")
        if not is_pkg:
            parts = parts[:-1]
        if imp.level > 1:
            parts = parts[: len(parts) - (imp.level - 1)] if imp.level - 1 <= len(parts) else []
        if imp.module:
            parts = [*parts, *imp.module.split(".")]
        return ".".join(parts)

    def _import_target(self, pf: ParsedFile, imp: Import, name: str | None, depth: int) -> Target | None:
        if not imp.is_from:
            dotted = imp.module if imp.alias else imp.module.split(".")[0]
            return Target("module", dotted) if self._module_exists(dotted) else EXTERNAL
        base = self._relative_base(pf, imp)
        assert name is not None
        sub = f"{base}.{name}" if base else name
        if sub in self._mod_prefixes:
            return Target("module", sub)
        if base and self._module_exists(base):
            return self.attr(Target("module", base), name, depth + 1)
        return EXTERNAL

    # ------------------------------------------------------------------ names
    def _scopes(self, path: str, scope: str | None) -> list[str | None]:
        """Innermost-first function scopes visible from ``scope`` (class bodies are skipped,
        except the class body itself when the code runs there)."""
        out: list[str | None] = []
        q = scope
        first = True
        while q is not None:
            kind = self._kinds.get(node_id(path, q))
            if kind in ("function", "method") or (first and kind == "class"):
                out.append(q)
            first = False
            q = q.rpartition(".")[0] or None
        out.append(None)
        return out

    def _typed(self, path: str, scope: str | None, spec: str, depth: int) -> Target | None:
        """Instance target for ``ann:Type`` / ``call:callee`` bindings."""
        how, _, expr = spec.partition(":")
        if not expr or depth > 12:
            return None
        t = self.expr(path, scope, expr, depth + 1)
        if t is None or t.kind != "node":
            return EXTERNAL if t == EXTERNAL else None
        kind = self._kinds.get(t.ref)
        if kind == "class":
            return Target("instance", t.ref)
        if how == "call" and kind in ("function", "method"):
            d = self.index.definition(t.ref)
            if d is not None and d.returns:
                fpath = t.ref.rsplit("::", 1)[0]
                return self._typed(fpath, d.parent, f"ann:{d.returns}", depth + 1)
        return None

    def name(self, path: str, scope: str | None, name: str, depth: int = 0) -> Target | None:
        if depth > 12:
            return None
        pf = self._file_by_path[path]
        for s in self._scopes(path, scope):
            nid = self._scope_defs.get((path, s), {}).get(name)
            if nid is not None:
                return Target("node", nid)
            imp = self._imports.get((path, s), {}).get(name)
            if imp is not None:
                return self._import_target(pf, imp[0], imp[1], depth)
            if s is not None:
                d = self.index.definition(node_id(path, s))
                if d is not None and d.kind != "class":
                    if name in d.params:
                        return self._typed(path, d.parent, f"ann:{d.params[name]}", depth)
                    if name in d.locals:
                        return self._typed(path, s, d.locals[name], depth)
        assigned = pf.assignments.get(name)
        if assigned is not None:
            how, _, expr = assigned.partition(":")
            if expr != name:  # `str = str` style aliases fall through to builtins
                t = self.expr(path, None, expr, depth + 1)
                if how == "ref":
                    return t
                if t is not None and t.kind == "node" and self._kinds.get(t.ref) == "class":
                    return Target("instance", t.ref)
                return EXTERNAL if t == EXTERNAL else None
        for star in self._stars.get(path, []):
            base = self._relative_base(pf, star)
            if base in self._mods:
                t = self.attr(Target("module", base), name, depth + 1)
                if t is not None and t != EXTERNAL:
                    return t
        if name in _BUILTINS:
            return EXTERNAL
        if self._stars.get(path):
            return EXTERNAL
        return None

    def expr(self, path: str, scope: str | None, dotted: str, depth: int = 0) -> Target | None:
        parts = dotted.split(".")
        t = self.name(path, scope, parts[0], depth)
        for p in parts[1:]:
            if t is None or t == EXTERNAL:
                return t
            t = self.attr(t, p, depth + 1)
        return t

    def attr(self, target: Target, name: str, depth: int = 0) -> Target | None:
        if depth > 12:
            return None
        if target.kind == "external":
            return EXTERNAL
        if target.kind == "module":
            path = self.index.modules.get(target.ref)
            if path is not None:
                nid = self._scope_defs.get((path, None), {}).get(name)
                if nid is not None:
                    return Target("node", nid)
            sub = f"{target.ref}.{name}"
            if sub in self._mod_prefixes:
                return Target("module", sub)
            if path is not None:
                pf = self._file_by_path[path]
                if name in self._imports.get((path, None), {}) or name in pf.assignments \
                        or self._stars.get(path):
                    return self.name(path, None, name, depth + 1)
            return None
        if target.kind in ("node", "instance"):
            kind = self._kinds.get(target.ref)
            if kind != "class":
                return None
            member, external = self.member(target.ref, name)
            if member is not None:
                return Target("node", member)
            chain, _ = self.mro(target.ref)
            for c in chain:
                d = self.index.definition(c)
                if d is not None and name in d.attrs:
                    cpath = c.rsplit("::", 1)[0]
                    return self._typed(cpath, d.qualname, d.attrs[name], depth + 1)
            return EXTERNAL if external else None
        return None

    # ------------------------------------------------------------------ classes
    def mro(self, class_id: str) -> tuple[list[str], bool]:
        """Linearized class chain (left-to-right DFS) and whether it reaches outside the repo."""
        if class_id in self._mro:
            return self._mro[class_id]
        self._mro[class_id] = ([class_id], False)  # recursion guard for cyclic bases
        chain = [class_id]
        external = False
        path, qual = class_id.rsplit("::", 1)
        d = self.index.definition(class_id)
        if d is not None:
            for base in d.bases:
                if base in ("object",):
                    continue
                t = self.expr(path, d.parent, base)
                if t is not None and t.kind == "node" and self._kinds.get(t.ref) == "class":
                    sub, ext = self.mro(t.ref)
                    external = external or ext
                    for c in sub:
                        if c not in chain:
                            chain.append(c)
                else:
                    external = True
        self._mro[class_id] = (chain, external)
        return chain, external

    def member(self, class_id: str, name: str, skip_self: bool = False) -> tuple[str | None, bool]:
        chain, external = self.mro(class_id)
        for c in chain[1:] if skip_self else chain:
            m = self.index.member(c, name)
            if m is not None:
                return m, external
        return None, external

    def _enclosing_class(self, path: str, caller: str | None) -> str | None:
        q = caller
        while q:
            nid = node_id(path, q)
            if self._kinds.get(nid) == "class":
                return nid
            q = q.rpartition(".")[0]
        return None

    # ------------------------------------------------------------------ calls
    def callee(self, pf: ParsedFile, caller: str | None, callee: str) -> Target | None:
        if callee.startswith("<lit>"):
            return EXTERNAL  # a method of a str/list/dict literal
        if callee.startswith("<expr>"):
            return None
        if callee.startswith("super()."):
            cls = self._enclosing_class(pf.path, caller)
            if cls is None:
                return None
            m, external = self.member(cls, callee.split(".", 1)[1], skip_self=True)
            return Target("node", m) if m else (EXTERNAL if external else None)
        parts = callee.split(".")
        if callee == "cls" and caller is not None:
            cls = self._enclosing_class(pf.path, caller)
            if cls is not None:
                return Target("node", cls)
        if parts[0] in ("self", "cls") and caller is not None and len(parts) > 1:
            cls = self._enclosing_class(pf.path, caller)
            if cls is not None:
                t: Target | None = Target("instance" if parts[0] == "self" else "node", cls)
                for p in parts[1:]:
                    if t is None or t == EXTERNAL:
                        break
                    t = self.attr(t, p)
                return t
        return self.expr(pf.path, caller, callee)

    def callable_node(self, t: Target) -> Target | None:
        if t.kind == "node":
            kind = self._kinds.get(t.ref)
            if kind == "class":
                init, _ = self.member(t.ref, "__init__")
                return Target("node", init or t.ref)
            return t
        if t.kind == "instance":
            m, external = self.member(t.ref, "__call__")
            return Target("node", m) if m else (EXTERNAL if external else None)
        if t.kind == "external":
            return t
        return None

    def _infer(self, callee: str) -> str | None:
        if callee.startswith(("<expr>", "<lit>")):
            return None
        attr = callee.rsplit(".", 1)[-1]
        if "." not in callee or attr.startswith("__") or attr in _GENERIC or len(attr) < 4:
            return None
        candidates = [n for n in self.index.by_name.get(attr, []) if self._kinds.get(n) == "method"]
        return candidates[0] if len(candidates) == 1 else None

    def edges(self) -> list[Edge]:
        out: list[Edge] = []
        for pf in self.files:
            for call in pf.calls:
                src = node_id(pf.path, call.caller) if call.caller else module_node_id(pf.path)
                t = self.callee(pf, call.caller, call.callee)
                if t is not None:
                    t = self.callable_node(t)
                if t is None and "." in call.callee and call.callee.rsplit(".", 1)[1] in _GENERIC \
                        and not (call.callee.count(".") == 1 and call.callee.startswith(("self.", "cls."))) \
                        and call.callee.count(".") >= 1 and not self._infer(call.callee):
                    # `items.append(x)`, `self.options.get(k)`: a method of a builtin container or str
                    # on a value whose type is unknown. Counted as external, not as a resolution failure.
                    t = EXTERNAL
                if t is None:
                    guess = self._infer(call.callee)
                    out.append(Edge(src=src, dst=guess, kind="call", line=call.line, name=call.callee,
                                    resolved=False, inferred=guess is not None))
                elif t.kind == "external":
                    out.append(Edge(src=src, dst=None, kind="call", line=call.line, name=call.callee,
                                    resolved=False, external=True))
                else:
                    out.append(Edge(src=src, dst=t.ref, kind="call", line=call.line, name=call.callee))
            seen_refs: set[tuple[str, str]] = set()
            for ref in pf.refs:
                src = node_id(pf.path, ref.caller) if ref.caller else module_node_id(pf.path)
                if ref.callee in ("self", "cls"):
                    continue
                t = self.callee(pf, ref.caller, ref.callee)
                if t is not None and t.kind == "node" and self._kinds.get(t.ref) in ("function", "method") \
                        and (src, t.ref) not in seen_refs and t.ref != src:
                    seen_refs.add((src, t.ref))
                    out.append(Edge(src=src, dst=t.ref, kind="ref", line=ref.line, name=ref.callee))
            for d in pf.definitions:
                if d.kind != "class":
                    continue
                cid = node_id(pf.path, d.qualname)
                for base in d.bases:
                    t = self.expr(pf.path, d.parent, base)
                    if t is not None and t.kind == "node" and self._kinds.get(t.ref) == "class":
                        out.append(Edge(src=cid, dst=t.ref, kind="inherit", line=d.start_line, name=base))
        return out

    def expr_in_module(self, module: str, dotted: str) -> str | None:
        """Node id for ``module:dotted`` references such as ``[project.scripts]`` values."""
        if not self._module_exists(module):
            return None
        t: Target | None = Target("module", module)
        for p in dotted.split("."):
            t = self.attr(t, p) if t is not None else None
        return t.ref if t is not None and t.kind == "node" else None

    def library_roots(self) -> list[str]:
        """Public names a package exports from its top-level ``__init__.py``: a library's API,
        which counts as reached even when no entry point calls it."""
        out: list[str] = []
        for pf in self.files:
            if not pf.path.endswith("__init__.py") or pf.module.count(".") > 1:
                continue
            names = set(self._imports.get((pf.path, None), {})) | set(self._scope_defs.get((pf.path, None), {}))
            for name in sorted(names):
                if name.startswith("_"):
                    continue
                t = self.name(pf.path, None, name)
                if t is not None and t.kind == "node":
                    out.append(t.ref)
        return sorted(set(out))
