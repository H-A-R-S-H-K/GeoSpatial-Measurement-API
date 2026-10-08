"""Fixtures shared by unit and API tests."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.main import create_app
from app.measurement_strategies.registry import MeasurementStrategyRegistry
from app.models.database import Database
from app.readers.factory import ReaderFactory, default_registrations
from app.repositories.file_repository import FileRepository
from app.repositories.measurement_repository import MeasurementRepository
from app.services.crs_service import CRSService
from app.services.file_service import FileService
from app.services.measurement_service import MeasurementService


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        temp_dir=str(tmp_path / "tmp"),
        max_upload_bytes=2_000_000,
        max_zip_uncompressed_bytes=20_000_000,
        max_zip_entries=64,
    )


@pytest.fixture
def database(settings: Settings) -> Database:
    db = Database(settings.resolved_database_url)
    db.init_schema()
    return db


@pytest.fixture
def session(database: Database) -> Iterator[Session]:
    db = database.session_factory()
    try:
        yield db
    finally:
        db.close()


def make_file_service(
    session: Session,
    settings: Settings,
    reader_factory: ReaderFactory | None = None,
) -> FileService:
    return FileService(
        session=session,
        file_repository=FileRepository(session),
        measurement_repository=MeasurementRepository(session),
        reader_factory=reader_factory or ReaderFactory(default_registrations(settings)),
        crs_service=CRSService(),
        measurement_service=MeasurementService(MeasurementStrategyRegistry.with_defaults()),
        settings=settings,
    )


@pytest.fixture
def file_service(session: Session, settings: Settings) -> FileService:
    return make_file_service(session, settings)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    application = create_app(settings)
    with TestClient(application) as test_client:
        yield test_client
