"""The same client interface over JSON-RPC (child process) and HTTP (Starlette TestClient)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from starlette.testclient import TestClient

from thrubase.api import Session
from thrubase.server import TOKEN_HEADER, create_app


class RemoteError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


class RpcClient:
    def __init__(self, root: Path, env: dict[str, str] | None = None) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "thrubase", "rpc"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env={**os.environ, **(env or {})},
        )
        self.next_id = 0
        self.notifications: list[dict[str, Any]] = []
        self.lock = threading.Lock()
        self.root = root

    def send(self, msg: dict[str, Any]) -> None:
        body = json.dumps(msg).encode()
        assert self.proc.stdin is not None
        self.proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
        self.proc.stdin.flush()

    def read(self) -> dict[str, Any]:
        assert self.proc.stdout is not None
        headers = {}
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise EOFError(self.proc.stderr.read().decode() if self.proc.stderr else "")
            line = line.strip()
            if not line:
                break
            k, _, v = line.decode().partition(":")
            headers[k.lower()] = v.strip()
        return json.loads(self.proc.stdout.read(int(headers["content-length"])))  # type: ignore[no-any-return]

    def request_id(self) -> int:
        self.next_id += 1
        return self.next_id

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        mid = self.request_id()
        self.send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
        return self.wait(mid)

    def wait(self, mid: int) -> Any:
        while True:
            msg = self.read()
            if "id" not in msg or msg.get("method"):
                self.notifications.append(msg)
                continue
            assert msg["id"] == mid
            if "error" in msg:
                raise RemoteError(msg["error"]["code"], msg["error"]["message"])
            return msg["result"]

    def initialize(self) -> Any:
        return self.call("initialize", {"root": str(self.root), "lang": "en", "clientVersion": "0.1.0"})

    def close(self) -> None:
        try:
            self.send({"jsonrpc": "2.0", "method": "exit"})
            self.proc.wait(10)
        finally:
            if self.proc.poll() is None:
                self.proc.kill()
            for f in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
                if f:
                    f.close()


class HttpClient:
    def __init__(self, root: Path) -> None:
        self.port = 8765
        self.token = "test-token"
        self.session = Session(root)
        self.app = create_app(self.session, self.token, self.port)
        self.client = TestClient(self.app, base_url=f"http://127.0.0.1:{self.port}")
        self.notifications: list[dict[str, Any]] = []

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        r = self.client.post(f"/api/{method}", json=params or {}, headers={TOKEN_HEADER: self.token})
        data = r.json()
        if "error" in data:
            raise RemoteError(data["error"]["code"], data["error"]["message"])
        return data["result"]

    def initialize(self) -> Any:
        return self.call("initialize", {"lang": "en", "clientVersion": "0.1.0"})

    def close(self) -> None:
        self.client.close()
