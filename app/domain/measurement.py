"""Measurement results produced by strategies and stored by the service."""

from dataclasses import dataclass
from typing import Any

from app.core.enums import MeasurementStatus, MeasurementUnit


@dataclass(frozen=True)
class MeasurementValue:
    """The numeric outcome of one strategy, without feature identity."""

    measurement: float | None
    unit: MeasurementUnit | None
    status: MeasurementStatus

    @classmethod
    def completed(cls, measurement: float, unit: MeasurementUnit) -> "MeasurementValue":
        return cls(measurement=measurement, unit=unit, status=MeasurementStatus.COMPLETED)

    @classmethod
    def not_required(cls) -> "MeasurementValue":
        return cls(measurement=None, unit=None, status=MeasurementStatus.NOT_REQUIRED)

    @classmethod
    def unsupported(cls) -> "MeasurementValue":
        return cls(measurement=None, unit=None, status=MeasurementStatus.UNSUPPORTED_GEOMETRY)

    @classmethod
    def invalid(cls) -> "MeasurementValue":
        return cls(measurement=None, unit=None, status=MeasurementStatus.INVALID_GEOMETRY)


@dataclass(frozen=True)
class FeatureMeasurement:
    """A measurement joined back to the feature it came from."""

    feature_id: int
    geometry_type: str
    measurement: float | None
    unit: MeasurementUnit | None
    status: MeasurementStatus
    properties: dict[str, Any]
