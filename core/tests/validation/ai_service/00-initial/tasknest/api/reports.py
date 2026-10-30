from fastapi import APIRouter, Depends

from ..db.session import Database
from ..models.user import User
from ..services.reports import ReportService
from .deps import get_current_user, get_db

router = APIRouter(prefix="/reports")


@router.get("/weekly/{project_id}")
def weekly(project_id: int, db: Database = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return ReportService(db).weekly_summary(project_id).as_dict()


@router.get("/burndown/{project_id}")
def burndown(project_id: int, db: Database = Depends(get_db), user: User = Depends(get_current_user)) -> list:
    return ReportService(db).burndown(project_id)
