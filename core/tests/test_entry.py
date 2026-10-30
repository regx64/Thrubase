"""C7: one fixture per entry-point pattern."""

from pathlib import Path

import pytest

from thrubase.engine.pipeline import Engine
from thrubase.store import Store

FIX = Path(__file__).parent / "fixtures" / "entries"


def entries(store: Store, name: str) -> dict[str, str | None]:
    m = Engine(FIX / name, store=store).build_map(no_cache=True)
    return {e: m.node(e).entry_kind for e in m.entries}


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        ("main_block", {"tool/run.py::<module>": "main-block"}),
        ("main_module", {"pkg/__main__.py::<module>": "main-module"}),
        ("scripts", {"src/scripts_pkg/cli.py::main": "script"}),
        ("flask_app", {"app.py::show_user": "route", "app.py::health": "route"}),
        ("fastapi_app", {"main.py::root": "route", "main.py::create_item": "route"}),
        ("django_app", {"blog/views.py::index": "django-url", "blog/views.py::PostView": "django-url"}),
        ("click_app", {"cli.py::cli": "cli", "cli.py::build": "cli", "cli.py::standalone": "cli"}),
        ("typer_app", {"main.py::hello": "cli"}),
        ("fallback", {"lib/ops.py::orchestrate": "fallback"}),
    ],
)
def test_entry_patterns(store: Store, fixture: str, expected: dict[str, str]) -> None:
    found = entries(store, fixture)
    if fixture == "fallback":
        # Public, zero in-degree, most outgoing calls first; private drivers never qualify.
        assert next(iter(found)) == "lib/ops.py::orchestrate"
        assert "lib/ops.py::_private_driver" not in found
        assert set(found.values()) == {"fallback"}
    else:
        assert found == expected


def test_unreachable_code_is_isolated(store: Store) -> None:
    m = Engine(Path(__file__).parent / "fixtures" / "calls_app", store=store).build_map(no_cache=True)
    assert m.isolated == ["app/store.py::unused_helper"]
    assert m.node("app/store.py::unused_helper").role == "isolated"
