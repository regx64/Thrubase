from dataclasses import dataclass
from datetime import datetime

from ..utils.dates import is_overdue, parse_date


@dataclass
class Task:
    id: int
    project_id: int
    owner_id: int
    title: str
    done: bool = False
    assignee_id: int | None = None
    due: str | None = None
    created: str = ""

    @classmethod
    def from_row(cls, row: dict) -> "Task":
        return cls(id=row["id"], project_id=row["project_id"], owner_id=row["owner_id"], title=row["title"],
                   done=bool(row["done"]), assignee_id=row["assignee_id"], due=row["due"], created=row["created"])

    def overdue(self, now: datetime) -> bool:
        if self.done or not self.due:
            return False
        return is_overdue(parse_date(self.due), now)

    def can_edit(self, user_id: int) -> bool:
        return user_id in (self.owner_id, self.assignee_id)
