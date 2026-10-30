import typer

from .app import create_app
from .config import load_settings
from .db.migrations import run_migrations
from .db.session import Database
from .services.reports import ReportService
from .workers.scheduler import Scheduler

app = typer.Typer(help="tasknest command line")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the HTTP API."""
    import uvicorn

    settings = load_settings()
    api = create_app(settings)
    uvicorn.run(api, host=host, port=port)


@app.command()
def migrate() -> None:
    """Create or upgrade the database schema."""
    settings = load_settings()
    db = Database(settings.database_url)
    applied = run_migrations(db)
    typer.echo(f"applied {applied} migrations")


@app.command()
def report(project_id: int) -> None:
    """Print the weekly summary for a project."""
    settings = load_settings()
    db = Database(settings.database_url)
    service = ReportService(db)
    summary = service.weekly_summary(project_id)
    typer.echo(summary.render())


@app.command()
def worker() -> None:
    """Run scheduled jobs (reminders, cleanups)."""
    settings = load_settings()
    scheduler = Scheduler(Database(settings.database_url), settings)
    scheduler.run_forever()
