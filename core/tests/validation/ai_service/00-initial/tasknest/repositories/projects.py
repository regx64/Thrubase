from ..models.project import Project
from .base import BaseRepository


class ProjectRepository(BaseRepository):
    table = "projects"

    def get(self, project_id: int) -> Project | None:
        row = self.fetch_one("SELECT * FROM projects WHERE id = ?", project_id)
        return Project.from_row(row) if row else None

    def for_owner(self, owner_id: int) -> list[Project]:
        return [Project.from_row(r) for r in self.fetch_all("SELECT * FROM projects WHERE owner_id = ?", owner_id)]

    def insert(self, owner_id: int, name: str) -> Project:
        project_id = self.db.execute("INSERT INTO projects (owner_id, name, archived) VALUES (?, ?, 0)", owner_id, name)
        project = self.get(project_id)
        assert project is not None
        return project

    def set_archived(self, project_id: int) -> None:
        self.db.execute("UPDATE projects SET archived = 1 WHERE id = ?", project_id)
