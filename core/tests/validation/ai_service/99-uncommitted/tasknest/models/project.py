from dataclasses import asdict, dataclass

from ..utils.text import make_slug


@dataclass
class Project:
    id: int
    owner_id: int
    name: str
    archived: bool = False

    @classmethod
    def from_row(cls, row: dict) -> "Project":
        return cls(id=row["id"], owner_id=row["owner_id"], name=row["name"], archived=bool(row["archived"]))

    @property
    def slug(self) -> str:
        return make_slug(self.name)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["slug"] = self.slug
        return data
