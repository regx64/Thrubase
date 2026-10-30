from ..core.errors import Forbidden, NotFound
from ..core.events import EventBus
from ..db.session import Database
from ..models.task import Task
from ..models.user import User
from ..models.label import Label
from ..repositories.labels import LabelRepository
from ..repositories.projects import ProjectRepository
from ..repositories.tasks import TaskRepository
from ..schemas.task import TaskIn
from ..utils.sorting import sort_by_priority


class TaskService:
    def __init__(self, db: Database, bus: EventBus) -> None:
        self.tasks = TaskRepository(db)
        self.projects = ProjectRepository(db)
        self.labels = LabelRepository(db)
        self.bus = bus

    def list_for_user(self, user: User) -> list[Task]:
        tasks = self.tasks.for_user(user.id)
        return sort_by_priority(tasks)

    def create(self, user: User, body: TaskIn) -> Task:
        project = self.projects.get(body.project_id)
        if project is None or project.archived:
            raise NotFound("project")
        return self.tasks.insert(project.id, user.id, body.title, body.due, body.priority)

    def _editable(self, user: User, task_id: int) -> Task:
        task = self.tasks.get(task_id)
        if task is None:
            raise NotFound("task")
        if not task.can_edit(user.id):
            raise Forbidden("not your task")
        return task

    def complete(self, user: User, task_id: int) -> Task:
        task = self._editable(user, task_id)
        if task.done:
            return task
        self.tasks.mark_done(task.id)
        task.done = True
        self._announce_completed(task, user)
        return task

    def _announce_completed(self, task: Task, user: User) -> None:
        payload = {"task_id": task.id, "user_id": user.id, "labels": [lb.name for lb in self.labels.for_task(task.id)]}
        self.bus.publish("task.completed", payload)

    def add_label(self, user: User, task_id: int, name: str) -> Label:
        task = self._editable(user, task_id)
        return self.labels.add(task.id, name.strip().lower())

    def assign(self, user: User, task_id: int, assignee_id: int) -> Task:
        task = self._editable(user, task_id)
        self.tasks.set_assignee(task.id, assignee_id)
        task.assignee_id = assignee_id
        return task

    def delete(self, user: User, task_id: int) -> None:
        task = self._editable(user, task_id)
        self.tasks.delete(task.id)
