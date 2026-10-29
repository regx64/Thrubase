# Thrubase

Climb a codebase. Thrubase reads a Python repository without running it, draws a
**terrain map** where altitude is how central the code is, and walks you along a **trail**
of 12–15 segments from the entry points to the summits. Each segment ends with a short
**checkpoint**. A **diff climb** does the same for uncommitted changes, which is the
fastest way to understand what an AI agent just did to your code.

* Code is never executed.
* Nothing is sent anywhere without a key. An optional LLM key (Anthropic, or any
  OpenAI-compatible endpoint such as Ollama) adds a two-sentence guide per segment;
  checkpoints work without it.

## Install

```bash
pipx install thrubase
```

VS Code: install **Thrubase** (`regx64.thrubase`) from the Marketplace or Open VSX. It uses
the CLI above.

## Use

```bash
thrubase map .                 # terrain map summary: entry points, top 10 by altitude
thrubase climb .               # full climb in the terminal (resumes where you stopped)
thrubase climb . --diff        # climb the uncommitted changes
thrubase climb . --since main  # climb everything since a revision
thrubase serve .               # local web UI on 127.0.0.1 (also: thrubase serve https://github.com/psf/requests)
thrubase config set lang ko    # 한국어
```

Progress is shared: a climb started in VS Code continues in `thrubase serve` and in the
terminal. Settings live in `~/.thrubase/config.toml` (`thrubase config path`);
`THRUBASE_HOME` moves the folder and `THRUBASE_API_KEY` provides the key.

| Exit code | Meaning |
| --- | --- |
| 0 | success |
| 1 | general error |
| 2 | invalid arguments |
| 3 | no files in a supported language |
| 4 | not a git repository (diff requests) |

## Repository

| Path | What |
| --- | --- |
| `core/` | PyPI package `thrubase`: engine, Python adapter, CLI, JSON-RPC and HTTP servers |
| `packages/map-view/` | shared UI (React + Vite): terrain map, climb screens, design system |
| `vscode/` | VS Code extension `regx64.thrubase` |
| `docs/gates/` | gate checklists and their recorded results |

Language-independent code lives only in `core/src/thrubase/engine/`; everything
Python-specific lives in `core/src/thrubase/adapters/python/`.

## Develop

```bash
cd core && python -m pip install -e ".[dev]"
ruff check src tests && mypy && pytest           # unit, property, git, RPC/HTTP, CLI
python tests/validation/fetch.py ~/.cache/tb && THRUBASE_VALIDATION_DIR=~/.cache/tb pytest -m golden
pytest -m perf -s                                 # synthetic 2,000-file repository
```

```bash
cd packages/map-view && npm ci && npm test && npm run build   # also copies into core/ and vscode/
npx playwright test                                            # screenshots, axe, frame time
```

```bash
cd vscode && npm ci && npm run test:unit && npm run build
THRUBASE_TEST_CLI=$(which thrubase) xvfb-run -a npm test       # @vscode/test-electron
```

License: AGPL-3.0.
