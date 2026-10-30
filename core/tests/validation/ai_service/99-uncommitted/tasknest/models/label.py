from dataclasses import dataclass

from ..utils.text import make_slug


@dataclass
class Label:
    id: int
    task_id: int
    name: str

    @classmethod
    def from_row(cls, row: dict) -> "Label":
        return cls(id=row["id"], task_id=row["task_id"], name=row["name"])

    @property
    def key(self) -> str:
        return make_slug(self.name)
