"""``~/.thrubase/``: ``config.toml``, ``cache/`` and ``progress/``.

VS Code and the web UI can run at the same time against the same repository, so every
read-modify-write goes through a file lock (``filelock``) and every write is atomic
(write to a temporary file, then ``os.replace``). ``THRUBASE_HOME`` moves the folder.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import tempfile
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, TypeVar

import tomli_w
from filelock import FileLock

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[import-not-found,unused-ignore]

T = TypeVar("T")

PROVIDERS = ("none", "anthropic", "openai-compatible")
LANGS = ("auto", "en", "ko")


@dataclass
class Config:
    lang: str = "auto"
    llm_provider: str = "none"
    llm_model: str = ""
    llm_endpoint: str = ""
    #: never read from or written to config.toml by default; comes from the environment
    api_key: str = field(default="", repr=False)
    max_files: int = 2000
    alpha: float = 0.5
    beta: float = 0.3
    gamma: float = 0.2
    extra_excludes: list[str] = field(default_factory=list)
    max_segments: int = 15
    summits: int = 6
    suggest_threshold: int = 5

    @property
    def weights(self) -> dict[str, float]:
        return {"alpha": self.alpha, "beta": self.beta, "gamma": self.gamma}


#: dotted config.toml key -> Config attribute
KEYS: dict[str, str] = {
    "lang": "lang",
    "llm.provider": "llm_provider",
    "llm.model": "llm_model",
    "llm.endpoint": "llm_endpoint",
    "llm.api_key": "api_key",
    "analysis.max_files": "max_files",
    "analysis.altitude.alpha": "alpha",
    "analysis.altitude.beta": "beta",
    "analysis.altitude.gamma": "gamma",
    "analysis.extra_excludes": "extra_excludes",
    "trail.max_segments": "max_segments",
    "trail.summits": "summits",
    "diff.suggest_threshold": "suggest_threshold",
}

ENV: dict[str, str] = {
    "THRUBASE_LANG": "lang",
    "THRUBASE_LLM_PROVIDER": "llm_provider",
    "THRUBASE_LLM_MODEL": "llm_model",
    "THRUBASE_LLM_ENDPOINT": "llm_endpoint",
    "THRUBASE_API_KEY": "api_key",
}

DEFAULT_TOML = """\
lang = "auto"                 # auto | en | ko

[llm]
provider = "none"             # none | anthropic | openai-compatible
model = ""                    # empty = provider default
endpoint = ""                 # for openai-compatible, e.g. http://localhost:11434/v1
# Keeping api_key out of this file is recommended. THRUBASE_API_KEY takes precedence.

[analysis]
max_files = 2000
altitude = { alpha = 0.5, beta = 0.3, gamma = 0.2 }
extra_excludes = []

[trail]
max_segments = 15
summits = 6

[diff]
suggest_threshold = 5
"""


class ConfigError(ValueError):
    pass


def _coerce(attr: str, value: Any) -> Any:
    default = getattr(Config(), attr)
    try:
        if isinstance(default, bool):
            return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes")
        if isinstance(default, int):
            return int(value)
        if isinstance(default, float):
            return float(value)
        if isinstance(default, list):
            if isinstance(value, list):
                return [str(v) for v in value]
            return [v.strip() for v in str(value).split(",") if v.strip()]
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"invalid value for {attr}: {value!r}") from exc
    value = str(value)
    if attr == "llm_provider" and value not in PROVIDERS:
        raise ConfigError(f"llm.provider must be one of {', '.join(PROVIDERS)}")
    if attr == "lang" and value not in LANGS:
        raise ConfigError(f"lang must be one of {', '.join(LANGS)}")
    return value


def _flatten(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in data.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flatten(v, key + "."))
        else:
            out[key] = v
    return out


class Store:
    def __init__(self, home: Path | str | None = None) -> None:
        env = os.environ.get("THRUBASE_HOME")
        self.home = Path(home or env or Path.home() / ".thrubase").expanduser()
        self.cache = self.home / "cache"
        self.progress_dir = self.home / "progress"

    # ------------------------------------------------------------------ files
    @property
    def config_path(self) -> Path:
        return self.home / "config.toml"

    def lock(self, path: Path) -> FileLock:
        path.parent.mkdir(parents=True, exist_ok=True)
        return FileLock(str(path) + ".lock", timeout=30)

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
            for attempt in range(10):
                try:
                    os.replace(tmp, path)
                    break
                except PermissionError:  # pragma: no cover - Windows: reader holds the file briefly
                    if attempt == 9:
                        raise
                    time.sleep(0.05 * (attempt + 1))
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)

    def read_json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def write_json(self, path: Path, data: Any) -> None:
        with self.lock(path):
            self._atomic_write(path, json.dumps(data, ensure_ascii=False, separators=(",", ":")))

    def update_json(self, path: Path, fn: Callable[[Any], T]) -> T:
        """Read-modify-write under the file lock. ``fn`` receives the current value (or None)
        and returns the new one."""
        with self.lock(path):
            current = self.read_json(path)
            new = fn(current)
            self._atomic_write(path, json.dumps(new, ensure_ascii=False, separators=(",", ":")))
            return new

    # ------------------------------------------------------------------ config
    def read_config_file(self) -> dict[str, Any]:
        try:
            return _flatten(tomllib.loads(self.config_path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return {}
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{self.config_path}: {exc}") from exc

    def load_config(self, overrides: dict[str, Any] | None = None) -> Config:
        """Precedence: argument > environment variable > config file > default."""
        cfg = Config()
        for key, value in self.read_config_file().items():
            if key in KEYS:
                setattr(cfg, KEYS[key], _coerce(KEYS[key], value))
        for env, attr in ENV.items():
            if os.environ.get(env):
                setattr(cfg, attr, _coerce(attr, os.environ[env]))
        if not cfg.api_key:
            fallback = {"anthropic": "ANTHROPIC_API_KEY", "openai-compatible": "OPENAI_API_KEY"}
            env_name = fallback.get(cfg.llm_provider)
            if env_name and os.environ.get(env_name):
                cfg.api_key = os.environ[env_name]
        for key, value in (overrides or {}).items():
            if value is None:
                continue
            attr = KEYS.get(key, key)
            if attr not in {f.name for f in fields(Config)}:
                raise ConfigError(f"unknown setting {key}")
            setattr(cfg, attr, _coerce(attr, value))
        return cfg

    def get_config_value(self, key: str) -> Any:
        if key not in KEYS:
            raise ConfigError(f"unknown setting {key}. Known: {', '.join(KEYS)}")
        if key == "llm.api_key":
            return "(set)" if self.load_config().api_key else ""
        return getattr(self.load_config(), KEYS[key])

    def set_config_value(self, key: str, value: str) -> None:
        if key not in KEYS:
            raise ConfigError(f"unknown setting {key}. Known: {', '.join(KEYS)}")
        coerced = _coerce(KEYS[key], value)
        with self.lock(self.config_path):
            try:
                data = tomllib.loads(self.config_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                data = tomllib.loads(DEFAULT_TOML)
            node = data
            parts = key.split(".")
            for p in parts[:-1]:
                node = node.setdefault(p, {})
            node[parts[-1]] = coerced
            self._atomic_write(self.config_path, tomli_w.dumps(data))

    def ensure_config(self) -> Path:
        if not self.config_path.exists():
            with self.lock(self.config_path):
                if not self.config_path.exists():
                    self._atomic_write(self.config_path, DEFAULT_TOML)
        return self.config_path

    # ------------------------------------------------------------------ repository data
    @staticmethod
    def repo_key(root: Path) -> str:
        norm = str(root.resolve()).replace("\\", "/")
        if os.name == "nt":  # pragma: no cover
            norm = norm.lower()
        return hashlib.sha256(norm.encode()).hexdigest()[:16]

    def repo_cache(self, root: Path) -> Path:
        return self.cache / "repos" / self.repo_key(root)

    def map_path(self, root: Path, snapshot: str) -> Path:
        return self.repo_cache(root) / "maps" / f"{snapshot}.json"

    def save_map(self, root: Path, snapshot: str, data: dict[str, Any], keep: int = 3) -> None:
        path = self.map_path(root, snapshot)
        self.write_json(path, data)
        maps = sorted(path.parent.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in maps[keep:]:
            with contextlib.suppress(OSError):
                old.unlink()

    def load_map(self, root: Path, snapshot: str) -> dict[str, Any] | None:
        data = self.read_json(self.map_path(root, snapshot))
        return data if isinstance(data, dict) else None

    def parsed_path(self, root: Path) -> Path:
        return self.repo_cache(root) / "parsed.json"

    def trail_path(self, root: Path, trail_id: str) -> Path:
        return self.repo_cache(root) / "trails" / f"{trail_id}.json"

    def progress_path(self, root: Path, trail_id: str) -> Path:
        return self.progress_dir / self.repo_key(root) / f"{trail_id}.json"

    def current_path(self, root: Path) -> Path:
        return self.progress_dir / self.repo_key(root) / "current.json"

    def guide_path(self, key: str) -> Path:
        return self.cache / "guides" / key[:2] / f"{key}.json"

    @contextlib.contextmanager
    def repo_lock(self, root: Path) -> Iterator[None]:
        with self.lock(self.repo_cache(root) / "build"):
            yield
