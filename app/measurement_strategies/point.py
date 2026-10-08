"""Points are accepted and deliberately not measured."""

from typing import ClassVar

from shapely.geometry.base import BaseGeometry

from app.core.enums import GeometryType
from app.domain.measurement import MeasurementValue
from app.measurement_strategies.base import MeasurementStrategy, planar_geometry


class PointMeasurementStrategy(MeasurementStrategy):
    """A point has no area or length. A broken point is still reported as invalid."""

    geometry_type: ClassVar[str] = GeometryType.POINT.value

    def measure(self, geometry: BaseGeometry) -> MeasurementValue:
        if planar_geometry(geometry) is None:
            return MeasurementValue.invalid()
        return MeasurementValue.not_required()
