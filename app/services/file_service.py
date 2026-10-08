"""Orchestrate upload, parsing, CRS preparation, measurement, and persistence."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import FileStatus
from app.core.exceptions import (
    AppError,
    InvalidGeospatialFileError,
    StoredFileNotFoundError,
    UnsupportedFileFormatError,
    UploadTooLargeError,
)
from app.models.file import FileRecord
from app.models.measurement import MeasurementRecord
from app.readers.factory import ReaderFactory
from app.readers.feature_mapper import extract_features
from app.repositories.file_repository import FileRepository
from app.repositories.measurement_repository import MeasurementRepository
from app.services.crs_service import CRSService, format_crs
from app.services.measurement_service import MeasurementService
from app.utils.file_utils import extension_of, remove_file, sanitize_filename, write_bytes

logger = logging.getLogger(__name__)

_MAX_ERROR_LENGTH = 2000


@dataclass
class _DetectedCrs:
    original_crs: str | None = None
    measurement_crs: str | None = None


class FileService:
    """Run the processing pipeline for one upload and serve later reads from the database.

    The service commits the file row before parsing so a failure can still be
    retrieved. Temporary uploads are removed even when processing raises.
    """

    def __init__(
        self,
        session: Session,
        file_repository: FileRepository,
        measurement_repository: MeasurementRepository,
        reader_factory: ReaderFactory,
        crs_service: CRSService,
        measurement_service: MeasurementService,
        settings: Settings,
    ) -> None:
        self._session = session
        self._files = file_repository
        self._measurements = measurement_repository
        self._readers = reader_factory
        self._crs_service = crs_service
        self._measurement_service = measurement_service
        self._settings = settings

    def process_upload(self, filename: str, content: bytes) -> FileRecord:
        original_name = sanitize_filename(filename)
        extension = extension_of(original_name)
        if not self._readers.supports_extension(extension):
            supported = ", ".join(self._readers.supported_extensions())
            raise UnsupportedFileFormatError(
                f"Unsupported file type '{extension or '(none)'}'. Supported types: {supported}."
            )
        if not content:
            raise InvalidGeospatialFileError("Uploaded file is empty.")
        if len(content) > self._settings.max_upload_bytes:
            raise UploadTooLargeError(
                f"Upload exceeds the maximum size of {self._settings.max_upload_bytes} bytes."
            )

        file_id = str(uuid.uuid4())
        temp_path: Path | None = None
        detected = _DetectedCrs()
        persisted = False
        try:
            temp_path = write_bytes(
                self._settings.resolved_temp_dir,
                file_id,
                extension,
                content,
            )
            record = self._files.add(
                FileRecord(
                    id=file_id,
                    original_filename=original_name,
                    feature_count=0,
                    status=FileStatus.PROCESSING.value,
                    created_at=datetime.now(UTC),
                )
            )
            self._session.commit()
            persisted = True
            self._process(record, temp_path, detected)
            self._session.commit()
        except AppError as exc:
            if persisted:
                self._mark_failed(file_id, exc.message, detected)
                exc.file_id = file_id
            raise
        except Exception as exc:
            logger.exception("Unexpected failure processing file %s", file_id)
            if persisted:
                self._mark_failed(file_id, "The file could not be processed.", detected)
            raise InvalidGeospatialFileError(
                "The file could not be processed.",
                file_id=file_id if persisted else None,
            ) from exc
        finally:
            if temp_path is not None:
                remove_file(temp_path)
        logger.info(
            "Processed file %s (%s): %s features, %s -> %s",
            record.id,
            record.original_filename,
            record.feature_count,
            record.original_crs,
            record.measurement_crs,
        )
        return record

    def get_file(self, file_id: str) -> FileRecord:
        record = self._files.get(file_id)
        if record is None:
            raise StoredFileNotFoundError("No file exists with the given id.")
        return record

    def get_measurements(self, file_id: str) -> list[MeasurementRecord]:
        self.get_file(file_id)
        return self._measurements.list_for_file(file_id)

    def _process(self, record: FileRecord, path: Path, detected: _DetectedCrs) -> None:
        reader = self._readers.create(path)
        frame = reader.read(path)
        if frame.crs is not None:
            detected.original_crs = format_crs(frame.crs)
            record.original_crs = detected.original_crs
        prepared = self._crs_service.prepare(frame)
        detected.measurement_crs = prepared.measurement_crs
        record.measurement_crs = prepared.measurement_crs
        features = extract_features(prepared.geodataframe)
        results = self._measurement_service.measure(features)
        self._measurements.add_all(record.id, results)
        record.feature_count = len(results)
        record.status = FileStatus.COMPLETED.value
        record.error_message = None

    def _mark_failed(self, file_id: str, message: str, detected: _DetectedCrs) -> None:
        try:
            self._session.rollback()
            record = self._files.get(file_id)
            if record is None:
                return
            record.status = FileStatus.FAILED.value
            record.error_message = message[:_MAX_ERROR_LENGTH]
            record.feature_count = 0
            record.original_crs = detected.original_crs
            record.measurement_crs = detected.measurement_crs
            self._session.commit()
        except Exception:
            logger.exception("Could not persist failure status for file %s", file_id)
            self._session.rollback()
