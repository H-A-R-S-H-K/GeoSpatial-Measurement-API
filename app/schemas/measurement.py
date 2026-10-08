"""Measurement collection returned for a processed file."""

from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import MeasurementStatus, MeasurementUnit
from app.models.measurement import MeasurementRecord


class MeasurementItem(BaseModel):
    """One feature. Geometry is omitted; attributes are returned as JSON-safe properties."""

    feature_id: int = Field(description="Zero-based position of the feature in the parsed dataset.")
    geometry_type: str
    measurement: float | None = Field(
        description="Area in m² or length in m. Null when not measured."
    )
    unit: MeasurementUnit | None = None
    status: MeasurementStatus
    properties: dict[str, Any] = Field(
        default_factory=dict,
        description="Attribute columns from the source file, excluding geometry.",
    )

    @classmethod
    def from_record(cls, record: MeasurementRecord) -> "MeasurementItem":
        return cls(
            feature_id=record.feature_index,
            geometry_type=record.geometry_type,
            measurement=record.measurement,
            unit=MeasurementUnit(record.unit) if record.unit is not None else None,
            status=MeasurementStatus(record.status),
            properties=record.properties or {},
        )


class MeasurementListResponse(BaseModel):
    """Every feature measurement for one file, in feature order."""

    file_id: str
    measurements: list[MeasurementItem]
