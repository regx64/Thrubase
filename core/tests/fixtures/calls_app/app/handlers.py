from .store import fetch_users, ping


def health() -> str:
    if not ping():
        return "down"
    return "ok"


def users() -> str:
    rows = fetch_users()
    return ",".join(rows)
