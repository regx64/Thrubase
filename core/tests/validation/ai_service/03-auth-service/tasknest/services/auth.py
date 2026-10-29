from ..config import Settings, load_settings
from ..core.errors import Unauthorized
from ..core.security import create_token, decode_token, verify_password
from ..db.session import Database
from ..models.user import User
from ..repositories.users import UserRepository


class AuthService:
    def __init__(self, db: Database, settings: Settings | None = None) -> None:
        self.users = UserRepository(db)
        self.settings = settings or load_settings()

    def login(self, email: str, password: str) -> str:
        user = self.users.by_email(email)
        if user is None or not verify_password(password, user.password):
            raise Unauthorized("wrong email or password")
        return self.issue_token(user)

    def issue_token(self, user: User) -> str:
        return create_token(user.id, self.settings.secret_key, self.settings.token_ttl_minutes)

    def current_user(self, token: str) -> User:
        user_id = decode_token(token, self.settings.secret_key)
        user = self.users.get(user_id)
        if user is None:
            raise Unauthorized("unknown user")
        return user
