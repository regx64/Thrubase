import base64
import hashlib
import hmac
import json
import os
import time

from .errors import Unauthorized


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return base64.b64encode(salt + digest).decode()


def verify_password(password: str, stored: str) -> bool:
    raw = base64.b64decode(stored)
    salt, digest = raw[:16], raw[16:]
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return hmac.compare_digest(candidate, digest)


def create_token(user_id: int, secret: str, ttl_minutes: int) -> str:
    payload = {"sub": user_id, "exp": int(time.time()) + ttl_minutes * 60}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return f"{body}.{_sign(body, secret)}"


def decode_token(token: str, secret: str) -> int:
    body, _, signature = token.partition(".")
    if not hmac.compare_digest(signature, _sign(body, secret)):
        raise Unauthorized("bad signature")
    payload = json.loads(base64.urlsafe_b64decode(body))
    if payload["exp"] < time.time():
        raise Unauthorized("token expired")
    return int(payload["sub"])


def _sign(body: str, secret: str) -> str:
    return hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
