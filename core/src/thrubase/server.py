"""Starlette app for ``thrubase serve``: the built map-view plus ``/api/*``.

* Binds to ``127.0.0.1`` only; a free port is picked automatically.
* A random token per run is passed only in the URL (``/?token=…``); the page sends it back
  in the ``X-Thrubase-Token`` header. ``/api/*`` answers 401 without it.
* ``Origin`` (when present) and ``Host`` must be this server, so other web pages and DNS
  rebinding cannot call the localhost API (403).
"""

from __future__ import annotations

import hmac
import secrets
import socket
import threading
from importlib import resources
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .api import INVALID_PARAMS, ApiError, Session

TOKEN_HEADER = "x-thrubase-token"

FALLBACK_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Thrubase</title>
<style>body{font:13px/20px -apple-system,"Segoe UI",sans-serif;margin:32px;color:#1d1d22}</style></head>
<body><h1 style="font-size:20px">Thrubase</h1><p>The web UI was not built into this installation.
Build <code>packages/map-view</code> (<code>npm run build</code>) or install a released wheel.</p></body></html>"""


def web_dir() -> Path:
    return Path(str(resources.files("thrubase").joinpath("web")))


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Progress:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.latest: dict[str, Any] = {"stage": "idle", "done": 0, "total": 0}

    def __call__(self, method: str, params: dict[str, Any]) -> None:
        if method == "$/progress":
            with self.lock:
                self.latest = dict(params)


def create_app(session: Session, token: str, port: int, *, static: Path | None = None) -> Starlette:
    progress = Progress()
    session.notify = progress
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    allowed_origins = {f"http://{h}" for h in allowed_hosts}
    static = static or web_dir()
    api_lock = threading.Lock()

    def guard(request: Request) -> Response | None:
        host = request.headers.get("host", "")
        if host not in allowed_hosts:
            return JSONResponse({"error": {"code": 403, "message": "forbidden host"}}, status_code=403)
        origin = request.headers.get("origin")
        if origin is not None and origin not in allowed_origins:
            return JSONResponse({"error": {"code": 403, "message": "forbidden origin"}}, status_code=403)
        sent = request.headers.get(TOKEN_HEADER, "")
        if not sent or not hmac.compare_digest(sent, token):
            return JSONResponse({"error": {"code": 401, "message": "missing or invalid token"}}, status_code=401)
        return None

    async def api(request: Request) -> Response:
        denied = guard(request)
        if denied is not None:
            return denied
        method = request.path_params["method"]
        if method == "$/progress":
            with progress.lock:
                return JSONResponse({"result": progress.latest})
        try:
            params = await request.json() if (await request.body()) else {}
        except ValueError:
            return JSONResponse({"error": {"code": INVALID_PARAMS, "message": "body must be JSON"}}, status_code=400)
        if method == "initialize" and isinstance(params, dict):
            params.pop("root", None)  # the served root is fixed at start-up

        def call() -> Any:
            with api_lock:
                return session.dispatch(method, params)

        try:
            result = await run_in_threadpool(call)
        except ApiError as exc:
            return JSONResponse({"error": exc.to_json()}, status_code=400 if exc.code != -32601 else 404)
        return JSONResponse({"result": result})

    async def index(request: Request) -> Response:
        page = static / "index.html"
        if page.is_file():
            return FileResponse(page, headers={"Cache-Control": "no-store",
                                               "Content-Security-Policy": _CSP,
                                               "Referrer-Policy": "no-referrer"})
        return HTMLResponse(FALLBACK_HTML)

    routes: list[Any] = [
        Route("/", index),
        Route("/api/{method:path}", api, methods=["POST"]),
    ]
    if (static / "assets").is_dir():
        routes.append(Mount("/assets", app=StaticFiles(directory=static / "assets"), name="assets"))
    if (static / "fonts").is_dir():
        routes.append(Mount("/fonts", app=StaticFiles(directory=static / "fonts"), name="fonts"))
    return Starlette(routes=routes)


_CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")


def new_token() -> str:
    return secrets.token_urlsafe(24)
