from ..core.errors import ValidationFailed
from ..core.security import hash_password
from ..db.session import Database
from ..models.user import User
from ..repositories.users import UserRepository
from ..utils.text import is_email
from .auth import AuthService


class UserService:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.users = UserRepository(db)

    def register(self, email: str, password: str) -> User:
        if not is_email(email):
            raise ValidationFailed("invalid email")
        if len(password) < 8:
            raise ValidationFailed("password too short")
        if self.users.by_email(email) is not None:
            raise ValidationFailed("email taken")
        return self.users.insert(email, hash_password(password))

    def authenticate(self, email: str, password: str) -> str:
        return AuthService(self.db).login(email, password)
