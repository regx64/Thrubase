from fastapi import FastAPI

from .api import projects, reports, tasks, users
from .config import Settings
from .core.errors import install_error_handlers
from .core.events import EventBus
from .db.migrations import run_migrations
from .db.session import Database
from .logging_setup import configure_logging
from .services.notifications import NotificationService


def create_app(settings: Settings) -> FastAPI:
    logger = configure_logging()
    api = FastAPI(title="tasknest")
    db = Database(settings.database_url)
    bus = EventBus()
    notifications = NotificationService(settings)
    bus.subscribe("task.completed", notifications.on_task_completed)
    api.state.db = db
    api.state.bus = bus
    api.state.settings = settings
    install_error_handlers(api)
    for module in (tasks, projects, users, reports):
        api.include_router(module.router)

    @api.on_event("startup")
    def startup() -> None:
        run_migrations(db)
        logger.info("tasknest ready")

    return api
