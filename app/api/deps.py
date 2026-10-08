"""FastAPI dependencies. This module is the composition root for one request."""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.measurement_strategies.registry import MeasurementStrategyRegistry
from app.models.database import Database
from app.readers.factory import ReaderFactory, default_registrations
from app.repositories.file_repository import FileRepository
from app.repositories.measurement_repository import MeasurementRepository
from app.services.crs_service import CRSService
from app.services.file_service import FileService
from app.services.measurement_service import MeasurementService


async def get_file_service(request: Request) -> AsyncIterator[FileService]:
    """Open a session, build the service, and close the session after the response.

    The dependency is async so the session is created and used on the event-loop
    thread. SQLAlchemy sessions are not safe to hand across threads.
    """
    database: Database = request.app.state.database
    settings: Settings = request.app.state.settings
    session = database.session_factory()
    try:
        yield build_file_service(session, settings)
    finally:
        session.close()


def build_file_service(session: Session, settings: Settings) -> FileService:
    return FileService(
        session=session,
        file_repository=FileRepository(session),
        measurement_repository=MeasurementRepository(session),
        reader_factory=ReaderFactory(default_registrations(settings)),
        crs_service=CRSService(),
        measurement_service=MeasurementService(MeasurementStrategyRegistry.with_defaults()),
        settings=settings,
    )
