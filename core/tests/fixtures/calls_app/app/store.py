def connect() -> object:
    return object()


def ping() -> bool:
    conn = connect()
    return conn is not None


def fetch_users() -> list[str]:
    conn = connect()
    return query(conn, "select name from users")


def query(conn: object, sql: str) -> list[str]:
    return []


def unused_helper() -> None:
    return None
