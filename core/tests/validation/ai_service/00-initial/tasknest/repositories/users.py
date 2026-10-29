from ..models.user import User
from .base import BaseRepository


class UserRepository(BaseRepository):
    table = "users"

    def get(self, user_id: int) -> User | None:
        row = self.fetch_one("SELECT * FROM users WHERE id = ?", user_id)
        return User.from_row(row) if row else None

    def by_email(self, email: str) -> User | None:
        row = self.fetch_one("SELECT * FROM users WHERE email = ?", email)
        return User.from_row(row) if row else None

    def insert(self, email: str, password_hash: str) -> User:
        user_id = self.db.execute("INSERT INTO users (email, password) VALUES (?, ?)", email, password_hash)
        user = self.get(user_id)
        assert user is not None
        return user
