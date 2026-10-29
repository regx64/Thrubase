"""C6: name resolution. 100% on the resolution fixture."""

from pathlib import Path

from thrubase.engine.pipeline import Engine
from thrubase.store import Store

FIX = Path(__file__).parent / "fixtures"


def edges(store: Store, name: str) -> tuple[set[tuple[str, str, str]], object]:
    a = Engine(FIX / name, store=store).analyze(no_cache=True)
    return {(e.src.split("::")[1], str(e.dst).split("::")[1] if e.dst else "", e.kind) for e in a.edges}, a


def test_full_resolution_on_fixture(store: Store) -> None:
    found, a = edges(store, "resolve_pkg")
    m = a.map  # type: ignore[attr-defined]
    assert m.stats.resolution_rate == 1.0
    unresolved = [e for e in a.edges if not e.resolved and not e.external]  # type: ignore[attr-defined]
    assert unresolved == []
    expect = {
        ("Base.total", "Base.sum_items", "call"),          # self.m() (Cart overrides at runtime)
        ("Cart.sum_items", "Base.sum_items", "call"),       # super().m()
        ("Cart.sum_items", "add", "call"),                  # from x import y as z
        ("Cart.sum_items", "parse", "call"),                # from . import util; module attribute
        ("Cart.checkout.inner", "format_price", "call"),    # util.money.format_price via package attribute
        ("Cart.checkout.inner", "Base.total", "call"),      # self in a nested function
        ("Cart.checkout", "Cart.checkout.inner", "call"),   # nested function
        ("Cart.checkout", "add", "call"),                   # import a.b.c as d
        ("Cart.checkout", "Money.__init__", "call"),        # constructor -> __init__
        ("Cart.checkout", "Helper.log", "call"),            # self.attr typed by self.helper = Helper()
        ("Cart.checkout", "Gateway.charge", "call"),        # annotated parameter gw: Gateway
        ("Cart.checkout", "Gateway.charge", "call"),        # class annotation `gateway: Gateway` wins
        ("Cart.__init__", "CardGateway", "call"),           # class without __init__ in the repo
        ("Base.create", "Base.empty", "call"),              # cls.m()
        ("Base.empty", "Base", "call"),                     # cls()
        ("Helper.log", "Helper.write", "call"),             # Class.staticmethod()
        ("CardGateway.charge", "Gateway.validate", "call"),  # inheritance chain (grandparent)
        ("CardGateway.charge", "Gateway.charge", "call"),   # super() through a middle class
        ("Gateway.validate", "Money.positive", "call"),     # annotated parameter amount: Money
        ("build", "Base.create", "call"),                   # inherited classmethod via subclass
        ("CardGateway", "Middle", "inherit"),
        ("Middle", "Gateway", "inherit"),
        ("Cart", "Base", "inherit"),
    }
    missing = expect - found
    assert not missing, missing


def test_reexport_and_library_roots(store: Store) -> None:
    _, a = edges(store, "resolve_pkg")
    m = a.map  # type: ignore[attr-defined]
    assert "shop/cart.py::Cart" in m.library
    assert "shop/util/money.py::format_price" in m.library


def test_external_and_unknown(tmp_path: Path, store: Store) -> None:
    (tmp_path / "m.py").write_text(
        "import os\nfrom json import loads\n\n"
        "def f(x):\n    os.path.join('a')\n    loads('1')\n    print(1)\n    x.whatever_unique_name()\n"
        "    items = []\n    items.append(1)\n    'a'.join([])\n    mystery()\n"
    )
    a = Engine(tmp_path, store=store).analyze(no_cache=True)
    ext = [e.name for e in a.edges if e.external]
    unres = [e.name for e in a.edges if not e.resolved and not e.external]
    assert a.map.stats.external_calls == 5  # os.path.join, loads, print, items.append, 'a'.join
    assert ext == []  # external calls are dropped from the Map
    assert sorted(unres) == ["mystery", "x.whatever_unique_name"]


def test_inferred_unique_method(tmp_path: Path, store: Store) -> None:
    (tmp_path / "m.py").write_text(
        "class Engine:\n    def ignite_rocket(self):\n        pass\n\n"
        "def f(e):\n    e.ignite_rocket()\n"
    )
    a = Engine(tmp_path, store=store).analyze(no_cache=True)
    (edge,) = [e for e in a.edges if e.name == "e.ignite_rocket"]
    assert edge.inferred and not edge.resolved and edge.dst == "m.py::Engine.ignite_rocket"
