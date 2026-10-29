"""Six entry-point patterns for Python, plus a fallback.

1. ``if __name__ == "__main__":`` blocks
2. ``__main__.py`` files
3. ``[project.scripts]`` (and Poetry ``[tool.poetry.scripts]``) in ``pyproject.toml``
4. FastAPI · Flask routes (``@app.route``, ``@router.get`` …)
5. Django ``urlpatterns``
6. click · typer commands

If none match, public module-level functions with zero in-degree and the most outgoing
calls become candidates.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from ...engine.index import SymbolIndex, module_node_id, node_id
from ...engine.parse import ParsedFile
from ...model import Edge
from ..base import Entry

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[import-not-found,unused-ignore]

_ROUTE_METHODS = "route|get|post|put|delete|patch|head|options|websocket|api_route|trace"
_ROUTE = re.compile(rf"^([A-Za-z_][\w.]*)\.({_ROUTE_METHODS})\(")
_WEB_FACTORIES = ("Flask", "FastAPI", "APIRouter", "Blueprint", "Quart", "Sanic", "Starlette", "Router")
_WEB_NAMES = {"app", "application", "router", "bp", "blueprint", "api", "api_router"}
_CLI_DIRECT = re.compile(r"^(click|typer|asyncclick|cloup)\.(command|group)\b")
_CLI_MEMBER = re.compile(r"^([A-Za-z_]\w*)\.(command|group)\b")
_CLI_FACTORIES = ("Typer", "Group", "group", "command")
_FALLBACK_COUNT = 3


def _scripts(root: Path) -> list[tuple[str, str]]:
    path = root / "pyproject.toml"
    if not path.is_file():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return []
    found: dict[str, str] = {}
    for table in (data.get("project", {}).get("scripts", {}),
                  data.get("project", {}).get("gui-scripts", {}),
                  data.get("tool", {}).get("poetry", {}).get("scripts", {})):
        if isinstance(table, dict):
            for name, ref in table.items():
                if isinstance(ref, str):
                    found.setdefault(name, ref)
                elif isinstance(ref, dict) and isinstance(ref.get("reference"), str):
                    found.setdefault(name, ref["reference"])
    return sorted(found.items())


def detect_entries(files: list[ParsedFile], index: SymbolIndex, root: Path, edges: list[Edge]) -> list[Entry]:
    from .resolve import Resolver

    resolver = Resolver(files, index)
    found: dict[str, Entry] = {}

    def add(nid: str | None, kind: str, detail: str = "") -> None:
        if nid is not None and nid not in found:
            found[nid] = Entry(node=nid, kind=kind, detail=detail)

    # 3. [project.scripts]
    for name, ref in _scripts(root):
        mod, _, attr = ref.partition(":")
        attr = attr.split("[")[0].strip()
        t = resolver.expr_in_module(mod.strip(), attr) if attr else None
        if t is not None:
            add(t, "script", name)

    for pf in sorted(files, key=lambda f: f.path):
        # 1. __main__ block
        if "main_block" in pf.extra:
            add(module_node_id(pf.path), "main-block", f"{pf.path}:{pf.extra['main_block'][0]}")
        # 2. __main__.py
        if pf.path.endswith("__main__.py"):
            add(module_node_id(pf.path), "main-module", pf.path)

        group_functions = {
            d.name for d in pf.definitions
            if any(_CLI_DIRECT.match(dec) and ".group" in dec for dec in d.decorators)
            or any(_CLI_MEMBER.match(dec) and dec.split(".")[1].startswith("group") for dec in d.decorators)
        }
        for d in pf.definitions:
            if d.kind not in ("function", "method") or not d.decorators:
                continue
            nid = node_id(pf.path, d.qualname)
            for dec in d.decorators:
                # 4. web routes
                m = _ROUTE.match(dec)
                if m:
                    obj = m.group(1).split(".")[0]
                    assigned = pf.assignments.get(obj, "")
                    if obj in _WEB_NAMES or any(assigned.endswith(f) or f".{f}" in assigned
                                                 for f in _WEB_FACTORIES):
                        add(nid, "route", dec.split("(", 1)[1].rstrip(")")[:60])
                        break
                # 6. click / typer
                if _CLI_DIRECT.match(dec):
                    add(nid, "cli", dec)
                    break
                m = _CLI_MEMBER.match(dec)
                if m:
                    obj = m.group(1)
                    assigned = pf.assignments.get(obj, "")
                    if obj in group_functions or any(assigned.endswith(f) for f in _CLI_FACTORIES) \
                            or (obj in ("cli", "app") and "typer" in assigned.lower()):
                        add(nid, "cli", dec)
                        break
        # 5. Django urlpatterns
        for ref, _line in pf.extra.get("urlpatterns", []):
            target = resolver.expr(pf.path, None, str(ref))
            if target is not None and target.kind == "node":
                add(target.ref, "django-url", str(ref))

    if found:
        return list(found.values())

    # Fallback: public functions with zero in-degree and the most outgoing calls.
    indeg: Counter[str] = Counter()
    outdeg: Counter[str] = Counter()
    for e in edges:
        if e.dst is not None and e.kind == "call" and e.dst != e.src:
            indeg[e.dst] += 1
            outdeg[e.src] += 1
    candidates = []
    for pf in files:
        for d in pf.definitions:
            if d.kind == "function" and d.parent is None and not d.name.startswith("_"):
                nid = node_id(pf.path, d.qualname)
                if indeg[nid] == 0 and outdeg[nid] > 0:
                    candidates.append((-outdeg[nid], nid))
    candidates.sort()
    return [Entry(node=nid, kind="fallback", detail=f"{-neg} calls") for neg, nid in candidates[:_FALLBACK_COUNT]]
