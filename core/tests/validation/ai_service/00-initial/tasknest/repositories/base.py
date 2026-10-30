from typing import Any

from ..db.session import Database


class BaseRepository:
    table = ""

    def __init__(self, db: Database) -> None:
        self.db = db

    def fetch_one(self, sql: str, *params: Any) -> dict | None:
        rows = self.db.query(sql, *params)
        return dict(rows[0]) if rows else None

    def fetch_all(self, sql: str, *params: Any) -> list[dict]:
        return [dict(r) for r in self.db.query(sql, *params)]

    def delete(self, row_id: int) -> None:
        self.db.execute(f"DELETE FROM {self.table} WHERE id = ?", row_id)
