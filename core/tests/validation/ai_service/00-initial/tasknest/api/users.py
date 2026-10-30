from fastapi import APIRouter, Depends

from ..db.session import Database
from ..models.user import User
from ..schemas.user import Credentials, UserOut
from ..services.users import UserService
from .deps import get_current_user, get_db

router = APIRouter(prefix="/users")


@router.post("/register")
def register(body: Credentials, db: Database = Depends(get_db)) -> UserOut:
    user = UserService(db).register(body.email, body.password)
    return UserOut.from_model(user)


@router.post("/login")
def login(body: Credentials, db: Database = Depends(get_db)) -> dict:
    token = UserService(db).authenticate(body.email, body.password)
    return {"token": token}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.from_model(user)
