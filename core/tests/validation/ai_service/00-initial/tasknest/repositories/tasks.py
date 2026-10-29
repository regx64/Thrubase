from ..models.task import Task
from ..utils.dates import now_iso
from .base import BaseRepository


class TaskRepository(BaseRepository):
    table = "tasks"

    def get(self, task_id: int) -> Task | None:
        row = self.fetch_one("SELECT * FROM tasks WHERE id = ?", task_id)
        return Task.from_row(row) if row else None

    def for_user(self, user_id: int) -> list[Task]:
        rows = self.fetch_all("SELECT * FROM tasks WHERE owner_id = ? OR assignee_id = ?", user_id, user_id)
        return [Task.from_row(r) for r in rows]

    def for_project(self, project_id: int) -> list[Task]:
        return [Task.from_row(r) for r in self.fetch_all("SELECT * FROM tasks WHERE project_id = ?", project_id)]

    def insert(self, project_id: int, owner_id: int, title: str, due: str | None) -> Task:
        task_id = self.db.execute(
            "INSERT INTO tasks (project_id, owner_id, title, done, due, created) VALUES (?, ?, ?, 0, ?, ?)",
            project_id, owner_id, title, due, now_iso(),
        )
        task = self.get(task_id)
        assert task is not None
        return task

    def mark_done(self, task_id: int) -> None:
        self.db.execute("UPDATE tasks SET done = 1 WHERE id = ?", task_id)

    def set_assignee(self, task_id: int, assignee_id: int) -> None:
        self.db.execute("UPDATE tasks SET assignee_id = ? WHERE id = ?", assignee_id, task_id)

    def open_with_due_date(self) -> list[Task]:
        rows = self.fetch_all("SELECT * FROM tasks WHERE done = 0 AND due IS NOT NULL")
        return [Task.from_row(r) for r in rows]
