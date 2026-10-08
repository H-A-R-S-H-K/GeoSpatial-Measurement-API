"""LineString length in metres."""

import math
from typing import ClassVar

from shapely.geometry.base import BaseGeometry

from app.core.enums import GeometryType, MeasurementUnit
from app.domain.measurement import MeasurementValue
from app.measurement_strategies.base import MeasurementStrategy, planar_geometry

_LENGTH_DECIMALS = 3


class LineStringMeasurementStrategy(MeasurementStrategy):
    """Horizontal length of a single LineString. Altitude is ignored."""

    geometry_type: ClassVar[str] = GeometryType.LINE_STRING.value

    def measure(self, geometry: BaseGeometry) -> MeasurementValue:
        planar = planar_geometry(geometry)
        if planar is None or planar.geom_type != GeometryType.LINE_STRING.value:
            return MeasurementValue.invalid()
        length = float(planar.length)
        if not math.isfinite(length):
            return MeasurementValue.invalid()
        return MeasurementValue.completed(round(length, _LENGTH_DECIMALS), MeasurementUnit.METRES)
