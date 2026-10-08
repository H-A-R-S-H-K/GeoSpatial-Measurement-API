"""File resource returned by the upload and lookup endpoints."""

from pydantic import BaseModel, Field

from app.core.enums import FileStatus
from app.models.file import FileRecord


class FileSummary(BaseModel):
    """Metadata for one uploaded file. ``crs`` is the dataset CRS, not the CRS used to measure."""

    id: str = Field(description="Server-generated file identifier.")
    filename: str = Field(description="Original filename with any directory parts removed.")
    feature_count: int = Field(description="Number of features found in the file.")
    crs: str | None = Field(description="Coordinate reference system declared by the dataset.")
    measurement_crs: str | None = Field(
        description=(
            "Metre-based projected CRS used for area and length. Null when processing failed early."
        )
    )
    status: FileStatus
    error_message: str | None = Field(
        default=None,
        description="Why processing failed. Null when status is not FAILED.",
    )

    @classmethod
    def from_record(cls, record: FileRecord) -> "FileSummary":
        return cls(
            id=record.id,
            filename=record.original_filename,
            feature_count=record.feature_count,
            crs=record.original_crs,
            measurement_crs=record.measurement_crs,
            status=FileStatus(record.status),
            error_message=record.error_message,
        )
