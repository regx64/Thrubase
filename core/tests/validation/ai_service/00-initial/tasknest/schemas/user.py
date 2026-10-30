from dataclasses import dataclass

from ..models.user import User


@dataclass
class Credentials:
    email: str
    password: str


@dataclass
class UserOut:
    id: int
    email: str

    @classmethod
    def from_model(cls, user: User) -> "UserOut":
        return cls(id=user.id, email=user.email)
