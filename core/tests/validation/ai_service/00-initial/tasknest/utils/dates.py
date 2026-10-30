from datetime import datetime, timedelta


def parse_date(value: str) -> datetime:
    return datetime.fromisoformat(value)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def is_overdue(due: datetime, now: datetime) -> bool:
    return due < now


def week_bounds(now: datetime) -> tuple[datetime, datetime]:
    start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=7)
