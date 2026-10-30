from datetime import datetime, timedelta

from ..config import Settings
from ..db.session import Database
from ..repositories.tasks import TaskRepository
from ..repositories.users import UserRepository
from ..services.notifications import NotificationService
from ..utils.dates import parse_date


def due_soon(due: str, now: datetime, hours: int) -> bool:
    when = parse_date(due)
    return now <= when <= now + timedelta(hours=hours)


def send_due_reminders(db: Database, settings: Settings) -> int:
    tasks = TaskRepository(db).open_with_due_date()
    users = UserRepository(db)
    notifications = NotificationService(settings)
    now = datetime.now()
    sent = 0
    for task in tasks:
        if task.due is None or not due_soon(task.due, now, settings.reminder_hours):
            continue
        user = users.get(task.assignee_id or task.owner_id)
        if user is None:
            continue
        if notifications.send_email(user.email, f"Due soon: {task.title}", reminder_body(task.title, task.due)):
            sent += 1
    return sent


def reminder_body(title: str, due: str) -> str:
    return f"The task '{title}' is due at {due}."
