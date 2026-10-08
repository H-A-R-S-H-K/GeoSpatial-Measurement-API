"""Select a reader from the uploaded filename.

Registration is the extension point. Adding GeoJSON means a new reader class
plus one entry in ``default_registrations``. Existing readers and ``FileService``
stay as they are.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.core.config import Settings
from app.core.exceptions import UnsupportedFileFormatError
from app.readers.base import GeospatialReader
from app.readers.kml_reader import KMLReader
from app.readers.shapefile_reader import ShapefileReader


@dataclass(frozen=True)
class ReaderRegistration:
    """Bind a reader class to the constructor used for one upload."""

    reader_type: type[GeospatialReader]
    builder: Callable[[], GeospatialReader]

    @property
    def extensions(self) -> frozenset[str]:
        return self.reader_type.extensions


class ReaderFactory:
    """Choose a ``GeospatialReader`` from the file extension."""

    def __init__(self, registrations: Sequence[ReaderRegistration]) -> None:
        if not registrations:
            raise ValueError("At least one geospatial reader must be registered.")
        self._registrations = list(registrations)

    def supported_extensions(self) -> list[str]:
        extensions = {
            extension
            for registration in self._registrations
            for extension in registration.extensions
        }
        return sorted(extensions)

    def supports_extension(self, extension: str) -> bool:
        suffix = extension.lower()
        return any(suffix in registration.extensions for registration in self._registrations)

    def create(self, path: Path) -> GeospatialReader:
        suffix = path.suffix.lower()
        for registration in self._registrations:
            if suffix in registration.extensions:
                return registration.builder()
        supported = ", ".join(self.supported_extensions())
        raise UnsupportedFileFormatError(
            f"Unsupported file type '{suffix or '(none)'}'. Supported types: {supported}."
        )


def default_registrations(settings: Settings) -> list[ReaderRegistration]:
    """Readers shipped with the service. This is the only format switch."""

    def build_shapefile_reader() -> GeospatialReader:
        return ShapefileReader(
            max_entries=settings.max_zip_entries,
            max_uncompressed_bytes=settings.max_zip_uncompressed_bytes,
        )

    return [
        ReaderRegistration(KMLReader, KMLReader),
        ReaderRegistration(ShapefileReader, build_shapefile_reader),
    ]
