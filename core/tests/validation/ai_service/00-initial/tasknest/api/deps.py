from fastapi import Depends, Header, Request

from ..core.errors import Unauthorized
from ..core.security import decode_token
from ..db.session import Database
from ..models.user import User
from ..repositories.users import UserRepository


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_current_user(authorization: str = Header(""), db: Database = Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise Unauthorized("missing token")
    request_user_id = decode_token(authorization.removeprefix("Bearer "), db.secret_key)
    user = UserRepository(db).get(request_user_id)
    if user is None:
        raise Unauthorized("unknown user")
    return user
