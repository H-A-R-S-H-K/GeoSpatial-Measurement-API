"""ASGI application."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import router as api_router
from app.api.errors import register_exception_handlers
from app.core.config import Settings, get_settings
from app.models.database import Database

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API. Pass ``settings`` in tests to point at a throwaway database."""
    resolved = settings or get_settings()
    database = Database(resolved.resolved_database_url)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("Initializing database")
        app.state.database.init_schema()
        yield

    app = FastAPI(
        title="Geospatial File Measurement",
        version=__version__,
        summary="Measure polygon area and line length from KML and zipped Shapefile uploads.",
        description=(
            "Upload a .kml file or a .zip Shapefile. Geographic coordinates are "
            "transformed to a local metre-based projected CRS before area or length "
            "is calculated. Results are stored and can be read back after the upload."
        ),
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.database = database
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api")

    @app.get("/health", tags=["health"], summary="Liveness check")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
