"""stdio JSON-RPC 2.0 server for the VS Code extension.

Framing is the LSP base protocol (``Content-Length`` headers), which ``vscode-jsonrpc``
speaks natively. stdin/stdout are used in binary mode with UTF-8 fixed, so the console
code page (cp949 on Korean Windows) never matters. Requests run one at a time on a worker
thread while the reader thread keeps handling ``$/cancelRequest``; long requests report
``$/progress`` notifications.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import traceback
from typing import IO, Any

from .api import INTERNAL_ERROR, REQUEST_CANCELLED, ApiError, Session
from .engine.pipeline import Cancelled, CancelToken

PARSE_ERROR = -32700
INVALID_REQUEST = -32600


class RpcServer:
    def __init__(self, session: Session | None = None, reader: IO[bytes] | None = None,
                 writer: IO[bytes] | None = None) -> None:
        self.reader = reader or sys.stdin.buffer
        self.writer = writer or sys.stdout.buffer
        self._write_lock = threading.Lock()
        self._queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._tokens: dict[Any, CancelToken] = {}
        self._tokens_lock = threading.Lock()
        self.session = session or Session(notify=self.notify)
        self.session.notify = self.notify
        self._stopped = threading.Event()

    # ------------------------------------------------------------------ framing
    def _read_message(self) -> dict[str, Any] | None:
        headers: dict[str, str] = {}
        while True:
            line = self.reader.readline()
            if not line:
                return None
            line = line.rstrip(b"\r\n")
            if not line:
                if headers:
                    break
                continue
            key, _, value = line.decode("ascii", "replace").partition(":")
            headers[key.strip().lower()] = value.strip()
        length = int(headers.get("content-length", "0"))
        body = b""
        while len(body) < length:
            chunk = self.reader.read(length - len(body))
            if not chunk:
                return None
            body += chunk
        try:
            msg = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send({"jsonrpc": "2.0", "id": None, "error": {"code": PARSE_ERROR, "message": "parse error"}})
            return {}
        return msg if isinstance(msg, dict) else {}

    def _send(self, msg: dict[str, Any]) -> None:
        body = json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with self._write_lock:
            self.writer.write(b"Content-Length: %d\r\n\r\n" % len(body))
            self.writer.write(body)
            self.writer.flush()

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    # ------------------------------------------------------------------ loop
    def _worker(self) -> None:
        while True:
            msg = self._queue.get()
            if msg is None:
                return
            self._handle(msg)

    def _handle(self, msg: dict[str, Any]) -> None:
        mid = msg.get("id")
        method = msg.get("method")
        with self._tokens_lock:
            token = self._tokens.setdefault(mid, CancelToken()) if mid is not None else CancelToken()
        try:
            if token.cancelled:
                raise Cancelled()
            if method == "shutdown":
                result: Any = None
            else:
                result = self.session.dispatch(str(method), msg.get("params"), cancel=token)
            if mid is not None:
                self._send({"jsonrpc": "2.0", "id": mid, "result": result})
        except Cancelled:
            if mid is not None:
                self._send({"jsonrpc": "2.0", "id": mid,
                            "error": {"code": REQUEST_CANCELLED, "message": "request cancelled"}})
        except ApiError as exc:
            if mid is not None:
                self._send({"jsonrpc": "2.0", "id": mid, "error": exc.to_json()})
        except Exception as exc:  # pragma: no cover - defensive: keep serving
            traceback.print_exc(file=sys.stderr)
            if mid is not None:
                self._send({"jsonrpc": "2.0", "id": mid,
                            "error": {"code": INTERNAL_ERROR, "message": f"{type(exc).__name__}: {exc}"}})
        finally:
            with self._tokens_lock:
                self._tokens.pop(mid, None)

    def serve(self) -> int:
        worker = threading.Thread(target=self._worker, name="thrubase-rpc", daemon=True)
        worker.start()
        try:
            while not self._stopped.is_set():
                msg = self._read_message()
                if msg is None:
                    break
                if not msg:
                    continue
                if msg.get("jsonrpc") != "2.0" or "method" not in msg:
                    if "id" in msg:
                        self._send({"jsonrpc": "2.0", "id": msg.get("id"),
                                    "error": {"code": INVALID_REQUEST, "message": "invalid request"}})
                    continue
                method = msg["method"]
                if method == "$/cancelRequest":
                    target = (msg.get("params") or {}).get("id")
                    with self._tokens_lock:
                        self._tokens.setdefault(target, CancelToken()).cancel()
                    continue
                if method == "exit":
                    break
                if "id" in msg:
                    with self._tokens_lock:
                        self._tokens.setdefault(msg["id"], CancelToken())
                self._queue.put(msg)
        finally:
            self._queue.put(None)
            worker.join(timeout=30)
        return 0


def main() -> int:
    # Anything printed by accident must never reach the protocol stream.
    stdout = sys.stdout.buffer
    sys.stdout = sys.stderr
    return RpcServer(writer=stdout).serve()
