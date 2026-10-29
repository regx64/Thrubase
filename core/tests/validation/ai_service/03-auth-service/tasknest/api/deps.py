from fastapi import Depends, Header, Request

from ..core.errors import Unauthorized
from ..db.session import Database
from ..models.user import User
from ..services.auth import AuthService


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_current_user(authorization: str = Header(""), db: Database = Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise Unauthorized("missing token")
    return AuthService(db).current_user(authorization.removeprefix("Bearer "))
