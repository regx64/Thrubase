"""W1/W2/W5: localhost-only binding, token and Origin checks, path refusal."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

from thrubase.api import Session
from thrubase.server import TOKEN_HEADER, create_app, free_port

FIX = Path(__file__).parent / "fixtures"
PORT = 8766


@pytest.fixture
def client(copy_fixture) -> TestClient:  # type: ignore[no-untyped-def]
    app = create_app(Session(copy_fixture("calls_app")), "tok", PORT)
    return TestClient(app, base_url=f"http://127.0.0.1:{PORT}")


def test_token_required(client: TestClient) -> None:
    assert client.post("/api/initialize", json={}).status_code == 401
    assert client.post("/api/initialize", json={}, headers={TOKEN_HEADER: "wrong"}).status_code == 401
    assert client.post("/api/initialize", json={}, headers={TOKEN_HEADER: "tok"}).status_code == 200


def test_other_origin_forbidden(client: TestClient) -> None:
    r = client.post("/api/initialize", json={}, headers={TOKEN_HEADER: "tok", "Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/api/initialize", json={}, headers={TOKEN_HEADER: "tok", "Origin": f"http://127.0.0.1:{PORT}"})
    assert r.status_code == 200


def test_dns_rebinding_host_forbidden(copy_fixture) -> None:  # type: ignore[no-untyped-def]
    app = create_app(Session(copy_fixture("calls_app")), "tok", PORT)
    c = TestClient(app, base_url="http://attacker.example")
    assert c.post("/api/initialize", json={}, headers={TOKEN_HEADER: "tok"}).status_code == 403


def test_path_traversal_refused(client: TestClient) -> None:
    h = {TOKEN_HEADER: "tok"}
    for bad in ("../secret.py", "app/../../x.py", "/etc/passwd", "..\\x.py", "C:/Windows/win.ini"):
        r = client.post("/api/segment.code", json={"file": bad, "startLine": 1}, headers=h)
        assert r.status_code == 400, bad
        message = r.json()["error"]["message"]
        assert message == "path outside the repository" or "no such file" in message
    r = client.post("/api/segment.code", json={"file": "app/cli.py", "startLine": 5, "endLine": 6}, headers=h)
    assert r.status_code == 200
    assert r.json()["result"]["highlight"] == [5, 6]
    assert r.json()["result"]["startLine"] == 2


def test_index_served(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200 and "Thrubase" in r.text


def _external_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 9))  # TEST-NET; nothing is sent
            ip = s.getsockname()[0]
    except OSError:
        return None
    return None if ip.startswith("127.") else str(ip)


def test_serve_binds_loopback_only(copy_fixture) -> None:  # type: ignore[no-untyped-def]
    root = copy_fixture("calls_app")
    port = free_port()
    proc = subprocess.Popen([sys.executable, "-m", "thrubase", "serve", str(root), "--port", str(port), "--no-open"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=dict(os.environ))
    try:
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                httpx.get(f"http://127.0.0.1:{port}/", timeout=1)
                break
            except httpx.HTTPError:
                time.sleep(0.2)
        assert httpx.get(f"http://127.0.0.1:{port}/", timeout=2).status_code == 200
        ip = _external_ip()
        if ip is None:
            pytest.skip("no external interface")
        with pytest.raises(httpx.HTTPError):
            httpx.get(f"http://{ip}:{port}/", timeout=2)
    finally:
        proc.terminate()
        proc.wait(10)
        for f in (proc.stdout, proc.stderr):
            if f:
                f.close()
