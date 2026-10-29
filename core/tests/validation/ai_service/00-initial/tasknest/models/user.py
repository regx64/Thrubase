from dataclasses import dataclass


@dataclass
class User:
    id: int
    email: str
    password: str

    @classmethod
    def from_row(cls, row: dict) -> "User":
        return cls(id=row["id"], email=row["email"], password=row["password"])
