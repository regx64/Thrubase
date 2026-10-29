import os
from dataclasses import dataclass


@dataclass
class Settings:
    database_url: str
    secret_key: str
    token_ttl_minutes: int = 60
    smtp_host: str = "localhost"
    reminder_hours: int = 24
    page_size: int = 20


def _env(name: str, default: str) -> str:
    return os.environ.get(f"TASKNEST_{name}", default)


def load_settings() -> Settings:
    settings = Settings(
        database_url=_env("DATABASE_URL", "sqlite:///tasknest.db"),
        secret_key=_env("SECRET_KEY", "dev-secret"),
        token_ttl_minutes=int(_env("TOKEN_TTL", "60")),
        smtp_host=_env("SMTP_HOST", "localhost"),
    )
    validate_settings(settings)
    return settings


def validate_settings(settings: Settings) -> None:
    if not settings.database_url.startswith("sqlite:///"):
        raise ValueError("only sqlite is supported")
    if settings.token_ttl_minutes <= 0:
        raise ValueError("token TTL must be positive")
