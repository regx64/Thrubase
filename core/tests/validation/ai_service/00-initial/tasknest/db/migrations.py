from .session import Database

MIGRATIONS = [
    "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, email TEXT UNIQUE, password TEXT)",
    "CREATE TABLE IF NOT EXISTS projects (id INTEGER PRIMARY KEY, owner_id INTEGER, name TEXT, archived INTEGER)",
    "CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY, project_id INTEGER, owner_id INTEGER, "
    "assignee_id INTEGER, title TEXT, done INTEGER, due TEXT, created TEXT)",
    "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)",
]


def current_version(db: Database) -> int:
    rows = db.query("SELECT MAX(version) AS v FROM schema_version")
    return int(rows[0]["v"] or 0) if rows else 0


def run_migrations(db: Database) -> int:
    db.execute(MIGRATIONS[-1])
    start = current_version(db)
    for version, sql in enumerate(MIGRATIONS[start:], start=start + 1):
        db.execute(sql)
        db.execute("INSERT INTO schema_version (version) VALUES (?)", version)
    return len(MIGRATIONS) - start
