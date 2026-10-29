import smtplib
from email.message import EmailMessage
from typing import Any

from ..config import Settings
from ..logging_setup import configure_logging


class NotificationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.log = configure_logging()

    def on_task_completed(self, payload: dict[str, Any]) -> None:
        self.log.info("task %s completed by %s", payload["task_id"], payload["user_id"])

    def send_email(self, to: str, subject: str, body: str) -> bool:
        message = EmailMessage()
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        try:
            with smtplib.SMTP(self.settings.smtp_host) as smtp:
                smtp.send_message(message)
        except OSError:
            self.log.warning("could not send mail to %s", to)
            return False
        return True
