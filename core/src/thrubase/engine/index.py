"""SymbolIndex: definition name → Node id, plus module name → file lookups."""

from __future__ import annotations

from collections import defaultdict

from .parse import Definition, ParsedFile

MODULE_QUALNAME = "<module>"


def node_id(path: str, qualname: str) -> str:
    return f"{path}::{qualname}"


def module_node_id(path: str) -> str:
    return node_id(path, MODULE_QUALNAME)


def split_id(nid: str) -> tuple[str, str]:
    path, _, qual = nid.rpartition("::")
    return path, qual


class SymbolIndex:
    def __init__(self, files: list[ParsedFile]) -> None:
        self.files: dict[str, ParsedFile] = {f.path: f for f in files}
        self.modules: dict[str, str] = {}
        self.defs: dict[str, Definition] = {}
        self.by_file: dict[str, dict[str, str]] = defaultdict(dict)
        self.members: dict[str, dict[str, str]] = defaultdict(dict)
        self.by_name: dict[str, list[str]] = defaultdict(list)
        for f in sorted(files, key=lambda f: f.path):
            self.add_module(f.module, f.path)
            for d in f.definitions:
                nid = node_id(f.path, d.qualname)
                self.defs[nid] = d
                self.by_file[f.path][d.qualname] = nid
                self.by_name[d.name].append(nid)
                if d.parent is not None:
                    self.members[node_id(f.path, d.parent)].setdefault(d.name, nid)

    def add_module(self, module: str, path: str) -> None:
        # The first registration wins, so ``pkg/__init__.py`` and ``pkg.py`` cannot both own ``pkg``.
        self.modules.setdefault(module, path)

    def module_file(self, module: str) -> ParsedFile | None:
        path = self.modules.get(module)
        return self.files.get(path) if path else None

    def lookup(self, path: str, qualname: str) -> str | None:
        return self.by_file.get(path, {}).get(qualname)

    def definition(self, nid: str) -> Definition | None:
        return self.defs.get(nid)

    def member(self, class_id: str, name: str) -> str | None:
        return self.members.get(class_id, {}).get(name)
