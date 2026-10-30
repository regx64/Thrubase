"""C10/T11: store, file locks, config precedence."""

import json
import multiprocessing
import os
from pathlib import Path

import pytest

from thrubase.store import Config, ConfigError, Store


def _bump(home: str, n: int) -> None:
    store = Store(Path(home))
    path = store.progress_dir / "shared.json"
    for _ in range(n):
        store.update_json(path, lambda cur: {"count": (cur or {}).get("count", 0) + 1})


def test_concurrent_writes_from_two_processes(home: Path) -> None:
    ctx = multiprocessing.get_context("spawn")
    procs = [ctx.Process(target=_bump, args=(str(home), 40)) for _ in range(2)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(60)
        assert p.exitcode == 0
    data = json.loads((home / "progress" / "shared.json").read_text())
    assert data == {"count": 80}


def test_thrubase_home_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THRUBASE_HOME", str(tmp_path / "custom"))
    s = Store()
    assert s.home == tmp_path / "custom"
    assert s.ensure_config().is_file()
    assert "suggest_threshold = 5" in s.config_path.read_text()


def test_config_precedence(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    assert store.load_config().llm_provider == "none"                       # default
    store.set_config_value("llm.provider", "anthropic")
    store.set_config_value("llm.model", "from-file")
    store.set_config_value("analysis.altitude.alpha", "0.7")
    cfg = store.load_config()
    assert (cfg.llm_provider, cfg.llm_model, cfg.alpha) == ("anthropic", "from-file", 0.7)  # file
    monkeypatch.setenv("THRUBASE_LLM_MODEL", "from-env")
    assert store.load_config().llm_model == "from-env"                     # env > file
    assert store.load_config({"llm.model": "from-arg"}).llm_model == "from-arg"  # arg > env
    assert store.get_config_value("llm.model") == "from-env"


def test_api_key_never_from_file_unless_set_and_env_first(store: Store, monkeypatch: pytest.MonkeyPatch) -> None:
    store.set_config_value("llm.provider", "anthropic")
    assert store.load_config().api_key == ""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "provider-var")
    assert store.load_config().api_key == "provider-var"
    monkeypatch.setenv("THRUBASE_API_KEY", "thrubase-var")
    assert store.load_config().api_key == "thrubase-var"
    assert store.get_config_value("llm.api_key") == "(set)"
    assert "thrubase-var" not in store.config_path.read_text()


def test_invalid_values(store: Store) -> None:
    with pytest.raises(ConfigError):
        store.set_config_value("llm.provider", "magic")
    with pytest.raises(ConfigError):
        store.set_config_value("nope", "1")
    with pytest.raises(ConfigError):
        store.set_config_value("trail.summits", "many")


def test_map_cache_keeps_latest(store: Store, tmp_path: Path) -> None:
    for i in range(5):
        store.save_map(tmp_path, f"snap{i}", {"i": i})
        os.utime(store.map_path(tmp_path, f"snap{i}"), (i + 1, i + 1))
    left = sorted(p.name for p in store.map_path(tmp_path, "x").parent.glob("*.json"))
    assert len(left) == 3
    assert store.load_map(tmp_path, "snap4") == {"i": 4}


def test_default_weights() -> None:
    assert Config().weights == {"alpha": 0.5, "beta": 0.3, "gamma": 0.2}
