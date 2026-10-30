"""C3: a fake adapter can be registered and runs through the pipeline."""

from __future__ import annotations

from pathlib import Path

import tree_sitter as ts
import tree_sitter_python as tsp

from thrubase.adapters.base import Entry, LanguageAdapter, Registry
from thrubase.engine.index import SymbolIndex, module_node_id, node_id
from thrubase.engine.parse import Call, Definition, ParsedFile
from thrubase.engine.pipeline import Engine
from thrubase.model import Edge
from thrubase.store import Store


class FakeAdapter:
    """Treats every non-empty line ``name -> other`` of a ``.fake`` file as a function
    ``name`` that calls ``other``."""

    name = "fake"
    version = "fake-1"
    extensions = (".fake",)
    excludes = ("ignored/",)

    def language(self) -> ts.Language:
        return ts.Language(tsp.language())  # any grammar; the query matches nothing useful

    def query_source(self) -> str:
        return "(module) @module"

    def module_name(self, path: str, all_paths: frozenset[str]) -> str:
        return path.rsplit(".", 1)[0].replace("/", ".")

    def extract(self, pf: ParsedFile, tree: ts.Tree, matches: list, source: bytes) -> None:  # type: ignore[type-arg]
        for i, line in enumerate(source.decode().splitlines(), start=1):
            if "->" not in line:
                continue
            name, other = (x.strip() for x in line.split("->"))
            if name not in {d.name for d in pf.definitions}:
                pf.definitions.append(Definition(qualname=name, name=name, kind="function", start_line=i, end_line=i))
            pf.calls.append(Call(caller=name, callee=other, line=i, end_line=i))

    def resolve(self, files: list[ParsedFile], index: SymbolIndex) -> list[Edge]:
        edges = []
        for pf in files:
            for c in pf.calls:
                dst = index.lookup(pf.path, c.callee)
                edges.append(Edge(src=node_id(pf.path, str(c.caller)), dst=dst, kind="call", line=c.line,
                                  name=c.callee, resolved=dst is not None))
        return edges

    def entries(self, files: list[ParsedFile], index: SymbolIndex, root: Path, edges: list[Edge]) -> list[Entry]:
        return [Entry(node=node_id(f.path, "main"), kind="fake") for f in files if index.lookup(f.path, "main")]

    def library_roots(self, files: list[ParsedFile], index: SymbolIndex) -> list[str]:
        return []


def test_fake_adapter_through_pipeline(tmp_path: Path, store: Store) -> None:
    (tmp_path / "prog.fake").write_text("main -> load\nload -> parse\nparse -> load\nmain -> run\nrun -> x\n")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "skip.fake").write_text("a -> b\n")
    reg = Registry()
    adapter = FakeAdapter()
    assert isinstance(adapter, LanguageAdapter)
    reg.register(adapter)
    assert reg.for_path("x/prog.fake") is adapter
    assert reg.for_path("x/prog.py") is None
    m = Engine(tmp_path, store=store, registry=reg).build_map()
    ids = {n.id for n in m.nodes}
    expected = {"prog.fake::main", "prog.fake::load", "prog.fake::parse", "prog.fake::run",
                module_node_id("prog.fake")}
    assert expected == ids
    assert m.entries == ["prog.fake::main"]
    assert m.repo.languages == ["fake"]
    assert m.stats.files == 1
    assert m.stats.resolved_calls == 4
    reg.unregister("fake")
    assert reg.names == []
