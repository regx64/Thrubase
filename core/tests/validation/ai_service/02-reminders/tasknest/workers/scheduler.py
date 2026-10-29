import time
from collections.abc import Callable

from ..config import Settings
from ..db.session import Database
from ..logging_setup import configure_logging
from .reminders import send_due_reminders


class Scheduler:
    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.log = configure_logging()
        self.jobs: list[tuple[int, Callable[[], None]]] = []
        self.register_defaults()

    def register_defaults(self) -> None:
        self.every(3600, self.cleanup)
        self.every(900, self.reminders)

    def reminders(self) -> None:
        sent = send_due_reminders(self.db, self.settings)
        self.log.info("sent %s reminders", sent)

    def every(self, seconds: int, job: Callable[[], None]) -> None:
        self.jobs.append((seconds, job))

    def cleanup(self) -> None:
        self.db.execute("DELETE FROM tasks WHERE done = 1 AND created < date('now', '-90 day')")

    def run_pending(self, tick: int) -> int:
        ran = 0
        for seconds, job in self.jobs:
            if tick % seconds == 0:
                job()
                ran += 1
        return ran

    def run_forever(self) -> None:
        tick = 0
        while True:
            self.run_pending(tick)
            time.sleep(1)
            tick += 1
