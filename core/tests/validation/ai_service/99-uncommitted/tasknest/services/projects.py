from ..core.errors import Forbidden, NotFound, ValidationFailed
from ..db.session import Database
from ..models.project import Project
from ..models.user import User
from ..repositories.projects import ProjectRepository


class ProjectService:
    def __init__(self, db: Database) -> None:
        self.projects = ProjectRepository(db)

    def list_for_owner(self, user: User) -> list[Project]:
        return [p for p in self.projects.for_owner(user.id) if not p.archived]

    def create(self, user: User, name: str) -> Project:
        clean = name.strip()
        if not clean:
            raise ValidationFailed("name is empty")
        return self.projects.insert(user.id, clean)

    def archive(self, user: User, project_id: int) -> Project:
        project = self.projects.get(project_id)
        if project is None:
            raise NotFound("project")
        if project.owner_id != user.id:
            raise Forbidden("not your project")
        self.projects.set_archived(project.id)
        project.archived = True
        return project
