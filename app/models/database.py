"""SQLAlchemy engine and session factory.

There is no process-wide engine. ``create_app`` stores a ``Database`` on
application state so tests can point at their own SQLite file.
"""

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for persistence models."""


class Database:
    """SQLite (or another SQLAlchemy URL) plus a session factory."""

    def __init__(self, url: str) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.url = url
        self.engine = create_engine(url, connect_args=connect_args)
        self.session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
        )

    def init_schema(self) -> None:
        _ensure_sqlite_directory(self.url)
        import app.models  # noqa: F401

        Base.metadata.create_all(self.engine)

    def session(self) -> Iterator[Session]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()


def _ensure_sqlite_directory(url: str) -> None:
    if not url.startswith("sqlite"):
        return
    database = make_url(url).database
    if not database or database == ":memory:":
        return
    Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection: object, _connection_record: object) -> None:
    module = type(dbapi_connection).__module__
    if "sqlite" not in module:
        return
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def main() -> None:
    """Create tables without starting the HTTP server."""
    from app.core.config import get_settings

    settings = get_settings()
    Database(settings.resolved_database_url).init_schema()


if __name__ == "__main__":
    main()
