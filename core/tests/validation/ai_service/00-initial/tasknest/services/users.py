from ..config import load_settings
from ..core.errors import Unauthorized, ValidationFailed
from ..core.security import create_token, hash_password, verify_password
from ..db.session import Database
from ..models.user import User
from ..repositories.users import UserRepository
from ..utils.text import is_email


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
        user = self.users.by_email(email)
        if user is None or not verify_password(password, user.password):
            raise Unauthorized("wrong email or password")
        settings = load_settings()
        return create_token(user.id, settings.secret_key, settings.token_ttl_minutes)
