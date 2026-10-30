from fastapi import APIRouter, Depends, Request

from ..db.session import Database
from ..models.user import User
from ..schemas.task import TaskIn, TaskOut, validate_task_in
from ..services.tasks import TaskService
from ..utils.pagination import paginate
from .deps import get_current_user, get_db

router = APIRouter(prefix="/tasks")


def _service(request: Request, db: Database) -> TaskService:
    return TaskService(db, request.app.state.bus)


@router.get("/")
def list_tasks(request: Request, page: int = 1, db: Database = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    service = _service(request, db)
    tasks = service.list_for_user(user)
    return paginate([TaskOut.from_model(t) for t in tasks], page, request.app.state.settings.page_size)


@router.post("/")
def create_task(request: Request, body: TaskIn, db: Database = Depends(get_db),
                user: User = Depends(get_current_user)) -> TaskOut:
    validate_task_in(body)
    task = _service(request, db).create(user, body)
    return TaskOut.from_model(task)


@router.post("/{task_id}/complete")
def complete_task(request: Request, task_id: int, db: Database = Depends(get_db),
                  user: User = Depends(get_current_user)) -> TaskOut:
    task = _service(request, db).complete(user, task_id)
    return TaskOut.from_model(task)


@router.post("/{task_id}/assign/{assignee_id}")
def assign_task(request: Request, task_id: int, assignee_id: int, db: Database = Depends(get_db),
                user: User = Depends(get_current_user)) -> TaskOut:
    task = _service(request, db).assign(user, task_id, assignee_id)
    return TaskOut.from_model(task)


@router.delete("/{task_id}")
def delete_task(request: Request, task_id: int, db: Database = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    _service(request, db).delete(user, task_id)
    return {"deleted": task_id}
