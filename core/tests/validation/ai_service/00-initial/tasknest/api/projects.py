from fastapi import APIRouter, Depends

from ..db.session import Database
from ..models.user import User
from ..services.projects import ProjectService
from .deps import get_current_user, get_db

router = APIRouter(prefix="/projects")


@router.get("/")
def list_projects(db: Database = Depends(get_db), user: User = Depends(get_current_user)) -> list:
    return [p.as_dict() for p in ProjectService(db).list_for_owner(user)]


@router.post("/")
def create_project(name: str, db: Database = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    project = ProjectService(db).create(user, name)
    return project.as_dict()


@router.post("/{project_id}/archive")
def archive_project(project_id: int, db: Database = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    project = ProjectService(db).archive(user, project_id)
    return project.as_dict()
