import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class Database:
    def __init__(self, url: str, secret_key: str = "dev-secret") -> None:
        self.path = url.removeprefix("sqlite:///")
        self.secret_key = secret_key
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def query(self, sql: str, *params: Any) -> list[sqlite3.Row]:
        return self.connect().execute(sql, params).fetchall()

    def execute(self, sql: str, *params: Any) -> int:
        with self.transaction() as conn:
            cursor = conn.execute(sql, params)
            return int(cursor.lastrowid or 0)
