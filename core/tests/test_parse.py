from pathlib import Path

from thrubase.adapters.python import PythonAdapter
from thrubase.engine.parse import Parser, content_hash, parsed_from_json, parsed_to_json

FIX = Path(__file__).parent / "fixtures" / "parse"


def parse(name: str, source: bytes | None = None):  # type: ignore[no-untyped-def]
    data = source if source is not None else (FIX / name).read_bytes()
    return Parser().parse(PythonAdapter(), name, data, name[:-3])


def test_shapes() -> None:
    pf = parse("shapes.py")
    defs = {d.qualname: d for d in pf.definitions}
    assert set(defs) >= {
        "deco", "deco.wrapper", "decorated", "fetch", "outer", "outer.middle", "outer.middle.inner",
        "Outer", "Outer.Inner", "Outer.Inner.method", "Outer.amethod", "Outer.value", "session",
    }
    assert defs["decorated"].decorators == ["deco", "functools.lru_cache(maxsize=None)"]
    assert defs["deco.wrapper"].decorators == ["functools.wraps(fn)"]
    assert defs["fetch"].is_async and defs["Outer.amethod"].is_async
    assert defs["Outer.amethod"].kind == "method"
    assert defs["Outer.Inner"].kind == "class" and defs["Outer.Inner"].parent == "Outer"
    assert defs["Outer.Inner.method"].kind == "method"
    assert defs["outer.middle.inner"].kind == "function"
    assert defs["outer.middle.inner"].parent == "outer.middle"
    # The setter redefinition keeps a distinct id; the first definition keeps the plain name.
    assert any(q.startswith("Outer.value@") for q in defs)
    # Line ranges (decorators excluded, 1-based, inclusive).
    assert (defs["decorated"].start_line, defs["decorated"].end_line) == (14, 15)
    assert (defs["Outer"].start_line, defs["Outer"].end_line) == (33, 47)
    calls = {(c.caller, c.callee) for c in pf.calls}
    assert ("outer", "middle") in calls
    assert ("outer.middle", "inner") in calls
    assert ("fetch", "s.get") in calls
    assert ("deco.wrapper", "fn") in calls
    assert ("fetch", "session") in calls
    kinds = {(s.kind, s.owner) for s in pf.spots}
    assert ("raise", "session") in kinds
    assert ("return", "outer.middle.inner") in kinds
    assert pf.errors == 0


def test_syntax_errors_still_extract() -> None:
    pf = parse("broken.py")
    names = {d.qualname for d in pf.definitions}
    assert "good_before" in names
    assert "StillHere.method" in names
    assert pf.errors >= 1
    assert ("StillHere.method", "good_before") in {(c.caller, c.callee) for c in pf.calls}


def test_crlf_and_lf_match() -> None:
    lf = (FIX / "shapes.py").read_bytes().replace(b"\r\n", b"\n")
    crlf = lf.replace(b"\n", b"\r\n")
    a, b = parse("shapes.py", lf), parse("shapes.py", crlf)
    assert content_hash(lf) == content_hash(crlf)
    assert a.content_hash == b.content_hash
    assert [(d.qualname, d.start_line, d.end_line, d.body_hash) for d in a.definitions] == \
        [(d.qualname, d.start_line, d.end_line, d.body_hash) for d in b.definitions]
    assert [(c.callee, c.line) for c in a.calls] == [(c.callee, c.line) for c in b.calls]


def test_comments_and_whitespace_do_not_change_body_hash() -> None:
    a = parse("x.py", b"def f(x):\n    return g(x)\n")
    b = parse("x.py", b"def f(x):\n    # explain\n\n    return   g( x )  # tail\n")
    c = parse("x.py", b"def f(x):\n    return h(x)\n")
    assert a.definitions[0].body_hash == b.definitions[0].body_hash
    assert a.definitions[0].body_hash != c.definitions[0].body_hash


def test_import_only_changes_keep_module_hash() -> None:
    a = parse("x.py", b"import os\nx = setup()\n")
    b = parse("x.py", b"import os\nimport sys\nx = setup()\n")
    assert a.extra["module_hash"] == b.extra["module_hash"]


def test_parse_cache_json_round_trip() -> None:
    pf = parse("shapes.py")
    back = parsed_from_json(parsed_to_json(pf))
    assert [d.qualname for d in back.definitions] == [d.qualname for d in pf.definitions]
    assert back.imports == pf.imports
    assert back.calls == pf.calls


def test_imports_extracted() -> None:
    pf = parse("x.py", b"import a.b\nimport c.d as e\nfrom ..f import g as h, i\nfrom . import j\nfrom k import *\n"
                       b"def fn():\n    import local\n")
    imps = [(i.module, i.level, i.names, i.alias, i.is_from, i.scope) for i in pf.imports]
    assert ("a.b", 0, [], None, False, None) in imps
    assert ("c.d", 0, [], "e", False, None) in imps
    assert ("f", 2, [("g", "h"), ("i", None)], None, True, None) in imps
    assert ("", 1, [("j", None)], None, True, None) in imps
    assert ("k", 0, [("*", None)], None, True, None) in imps
    assert ("local", 0, [], None, False, "fn") in imps
