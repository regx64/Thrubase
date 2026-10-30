from dataclasses import dataclass

from ..core.errors import ValidationFailed
from ..models.task import Task
from ..utils.dates import parse_date


@dataclass
class TaskIn:
    project_id: int
    title: str
    due: str | None = None


@dataclass
class TaskOut:
    id: int
    title: str
    done: bool
    due: str | None

    @classmethod
    def from_model(cls, task: Task) -> "TaskOut":
        return cls(id=task.id, title=task.title, done=task.done, due=task.due)


def validate_task_in(body: TaskIn) -> None:
    if not body.title.strip():
        raise ValidationFailed("title is empty")
    if body.due is not None:
        try:
            parse_date(body.due)
        except ValueError as exc:
            raise ValidationFailed("due must be an ISO date") from exc
