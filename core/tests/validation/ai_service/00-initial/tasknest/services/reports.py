from dataclasses import dataclass, field
from datetime import datetime

from ..core.errors import NotFound
from ..db.session import Database
from ..repositories.projects import ProjectRepository
from ..repositories.tasks import TaskRepository
from ..utils.dates import week_bounds


@dataclass
class Summary:
    project: str
    done: int
    open: int
    overdue: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"{self.project}: {self.done} done, {self.open} open"]
        lines += [f"  overdue: {title}" for title in self.overdue]
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {"project": self.project, "done": self.done, "open": self.open, "overdue": self.overdue}


class ReportService:
    def __init__(self, db: Database) -> None:
        self.tasks = TaskRepository(db)
        self.projects = ProjectRepository(db)

    def weekly_summary(self, project_id: int) -> Summary:
        project = self.projects.get(project_id)
        if project is None:
            raise NotFound("project")
        now = datetime.now()
        start, _end = week_bounds(now)
        tasks = [t for t in self.tasks.for_project(project_id) if t.created >= start.isoformat()]
        done = sum(1 for t in tasks if t.done)
        overdue = [t.title for t in tasks if t.overdue(now)]
        return Summary(project=project.name, done=done, open=len(tasks) - done, overdue=overdue)

    def burndown(self, project_id: int) -> list[int]:
        tasks = self.tasks.for_project(project_id)
        remaining = len(tasks)
        points = []
        for task in sorted(tasks, key=lambda t: t.created):
            if task.done:
                remaining -= 1
            points.append(remaining)
        return points
