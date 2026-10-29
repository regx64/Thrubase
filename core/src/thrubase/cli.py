"""``thrubase`` command line: map, climb, serve, rpc, config.

Exit codes: 0 success, 1 general error, 2 invalid arguments, 3 no files in a supported
language, 4 not a git repository (diff requests).
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import webbrowser
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .api import NO_CHANGES, NO_SUPPORTED_LANGUAGE, NOT_A_GIT_REPOSITORY, ApiError, Session
from .i18n import resolve_lang, t
from .store import KEYS, ConfigError, Store

EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_UNSUPPORTED = 3
EXIT_NOT_GIT = 4

app = typer.Typer(add_completion=False, no_args_is_help=True, rich_markup_mode=None,
                  pretty_exceptions_enable=False,
                  help="Climb a codebase: terrain map, trails and checkpoints.")
config_app = typer.Typer(no_args_is_help=True, help="Read and write settings.")
app.add_typer(config_app, name="config")


def _console() -> Console:
    return Console(highlight=False, soft_wrap=False)


def _err(message: str, code: int) -> typer.Exit:
    Console(stderr=True, highlight=False).print(f"[red]error:[/red] {message}")
    return typer.Exit(code)


def _exit_for(exc: ApiError) -> int:
    return {NO_SUPPORTED_LANGUAGE: EXIT_UNSUPPORTED, NOT_A_GIT_REPOSITORY: EXIT_NOT_GIT,
            NO_CHANGES: EXIT_ERROR}.get(exc.code, EXIT_ERROR)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"thrubase {__version__}")
        raise typer.Exit(0)


@app.callback()
def _main(
    version: Annotated[bool, typer.Option("--version", callback=_version, is_eager=True,
                                          help="Show the version and exit.")] = False,
) -> None:
    pass


def _root(path: Path) -> Path:
    if not path.exists() or not path.is_dir():
        raise _err(f"not a folder: {path}", EXIT_USAGE)
    return path.resolve()


@app.command("map")
def map_cmd(
    path: Annotated[Path, typer.Argument(help="Repository folder.")] = Path("."),
    as_json: Annotated[bool, typer.Option("--json", help="Print the Map JSON.")] = False,
    no_cache: Annotated[bool, typer.Option("--no-cache", help="Ignore cached results.")] = False,
    lang: Annotated[str | None, typer.Option("--lang", help="en | ko")] = None,
) -> None:
    """Build the terrain map; print a summary or the Map JSON."""
    root = _root(path)
    session = Session(root, lang=lang)
    try:
        m = session.dispatch("map.build", {"noCache": no_cache})
    except ApiError as exc:
        raise _err(exc.message, _exit_for(exc)) from exc
    if as_json:
        sys.stdout.write(json.dumps(m, ensure_ascii=False))
        sys.stdout.write("\n")
        return
    _print_summary(m, session.lang, session.config.max_files)


def _print_summary(m: dict[str, Any], lang: str, limit: int) -> None:
    c = _console()
    st = m["stats"]
    nodes = {n["id"]: n for n in m["nodes"]}
    c.print(f"[bold]{t(lang, 'cli.map.title', name=m['repo']['name'])}[/bold]")
    c.print(t(lang, "cli.map.files", files=st["files"], skipped=st["skipped_files"], limit=limit))
    c.print(t(lang, "cli.map.resolution", resolved=st["resolved_calls"],
              total=st["calls"] - st["external_calls"], rate=round(st["resolution_rate"] * 100, 1)))
    c.print(f"\n[bold]{t(lang, 'cli.map.entries')}[/bold]")
    if not m["entries"]:
        c.print("  " + t(lang, "cli.map.none"))
    for e in m["entries"]:
        n = nodes[e]
        label = n["qualname"] if n["qualname"] != "<module>" else n["file"]
        c.print(f"  {label}  [dim]{n['file']}:{n['start_line']} · {n.get('entry_kind') or ''}[/dim]")
    c.print(f"\n[bold]{t(lang, 'cli.map.top')}[/bold]")
    table = Table(show_header=False, box=None, pad_edge=False)
    top = sorted((n for n in m["nodes"] if n["kind"] != "module"), key=lambda n: (-n["h"], n["id"]))[:10]
    for i, n in enumerate(top, start=1):
        table.add_row(f"{i:>2}", f"{n['h']:.3f}", n["qualname"], f"[dim]{n['file']}:{n['start_line']}[/dim]")
    c.print(table)
    c.print(f"\n{t(lang, 'cli.map.isolated', count=len(m['isolated']))}")
    c.print(f"[dim]{t(lang, 'cli.map.time', seconds=st['seconds'])}[/dim]")


@app.command()
def climb(
    path: Annotated[Path, typer.Argument(help="Repository folder.")] = Path("."),
    diff: Annotated[bool, typer.Option("--diff", help="Climb the uncommitted changes.")] = False,
    since: Annotated[str | None, typer.Option("--since", metavar="REF", help="Diff against REF.")] = None,
    lang: Annotated[str | None, typer.Option("--lang", help="en | ko")] = None,
    restart: Annotated[bool, typer.Option("--restart", help="Start the trail over.")] = False,
) -> None:
    """Terminal climb; resumes a climb in progress."""
    from .tui import Climb

    if lang is not None and lang not in ("en", "ko", "auto"):
        raise _err("--lang must be en or ko", EXIT_USAGE)
    root = _root(path)
    session = Session(root, lang=lang)
    kind = "diff" if diff or since else "full"
    try:
        code = Climb(session).run(kind=kind, since=since, restart=restart)
    except ApiError as exc:
        raise _err(exc.message, _exit_for(exc)) from exc
    except (KeyboardInterrupt, EOFError):
        _console().print("\n" + t(session.lang, "climb.paused"))
        code = 0
    raise typer.Exit(code)


def _is_url(value: str) -> bool:
    return value.startswith(("https://github.com/", "http://github.com/", "github.com/", "git@github.com:"))


def _on_rm_error(func: Any, path: str, exc: Any) -> None:
    # Windows: files in .git/objects are read-only; clear the flag and retry.
    with contextlib.suppress(OSError):
        os.chmod(path, stat.S_IWRITE)
        func(path)


def remove_tree(path: Path) -> None:
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_on_rm_error)
    else:  # pragma: no cover
        shutil.rmtree(path, onerror=_on_rm_error)


def clone_public(url: str) -> Path:
    """``git clone --depth 1`` into a temporary folder. Nothing in it is ever executed."""
    if url.startswith("github.com/"):
        url = "https://" + url
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url.split(":", 1)[1]
    tmp = Path(tempfile.mkdtemp(prefix="thrubase-"))
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_LFS_SKIP_SMUDGE": "1"}
    git = shutil.which("git")
    if git is None:
        remove_tree(tmp)
        raise RuntimeError("git was not found")
    proc = subprocess.run(
        [git, "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=never", "clone", "--depth", "1",
         "--no-tags", "--single-branch", url, str(tmp / "repo")],
        capture_output=True, env=env, check=False,
    )
    if proc.returncode != 0:
        remove_tree(tmp)
        raise RuntimeError(proc.stderr.decode("utf-8", "replace").strip())
    return tmp


@app.command()
def serve(
    target: Annotated[str, typer.Argument(metavar="[PATH|URL]", help="Repository folder or public GitHub URL.")] = ".",
    port: Annotated[int, typer.Option("--port", help="Port (default: a free one).")] = 0,
    no_open: Annotated[bool, typer.Option("--no-open", help="Do not open the browser.")] = False,
    lang: Annotated[str | None, typer.Option("--lang", help="en | ko")] = None,
) -> None:
    """Local web UI."""
    import uvicorn

    from .server import create_app, free_port, new_token, web_dir

    lang_resolved = resolve_lang(lang)
    tmp: Path | None = None
    if _is_url(target):
        _console().print(t(lang_resolved, "serve.cloning", url=target))
        try:
            tmp = clone_public(target)
        except RuntimeError as exc:
            raise _err(f"{t(lang_resolved, 'serve.clone_failed', url=target)} {exc}", EXIT_ERROR) from exc
        root = tmp / "repo"
    else:
        root = _root(Path(target))
    try:
        port = port or free_port()
        token = new_token()
        session = Session(root, lang=lang)
        application = create_app(session, token, port)
        url = f"http://127.0.0.1:{port}/?token={token}"
        c = _console()
        if not (web_dir() / "index.html").is_file():
            c.print(f"[yellow]{t(session.lang, 'serve.missing_web')}[/yellow]")
        c.print(t(session.lang, "serve.listening", url=url))
        c.print(f"[dim]{t(session.lang, 'serve.stop')}[/dim]")
        if not no_open:
            threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        uvicorn.run(application, host="127.0.0.1", port=port, log_level="warning")
    finally:
        if tmp is not None:
            remove_tree(tmp)


@app.command()
def rpc() -> None:
    """stdio JSON-RPC server, for VS Code only."""
    from .rpc import main as rpc_main

    raise typer.Exit(rpc_main())


@config_app.command("get")
def config_get(key: Annotated[str, typer.Argument(help=f"One of: {', '.join(KEYS)}")]) -> None:
    """Print a setting (argument > environment variable > file > default)."""
    try:
        value = Store().get_config_value(key)
    except ConfigError as exc:
        raise _err(str(exc), EXIT_USAGE) from exc
    typer.echo(json.dumps(value) if isinstance(value, list) else str(value))


@config_app.command("set")
def config_set(key: str, value: str) -> None:
    """Write a setting to config.toml."""
    store = Store()
    if key == "llm.api_key":
        typer.echo(t(resolve_lang(None), "config.key_env"))
    try:
        store.set_config_value(key, value)
    except ConfigError as exc:
        raise _err(str(exc), EXIT_USAGE) from exc
    shown = "(set)" if key == "llm.api_key" else value
    typer.echo(t(resolve_lang(None), "config.saved", key=key, value=shown))


@config_app.command("path")
def config_path() -> None:
    """Show the config file location."""
    typer.echo(str(Store().ensure_config()))


def main() -> None:
    if os.name == "nt":  # pragma: no cover
        with contextlib.suppress(AttributeError, ValueError):
            sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
            sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        signal.signal(signal.SIGINT, signal.default_int_handler)
    app()


if __name__ == "__main__":
    main()
