"""Polygon area in square metres."""

import math
from typing import ClassVar

from shapely.geometry.base import BaseGeometry

from app.core.enums import GeometryType, MeasurementUnit
from app.domain.measurement import MeasurementValue
from app.measurement_strategies.base import MeasurementStrategy, planar_geometry

_AREA_DECIMALS = 3


class PolygonMeasurementStrategy(MeasurementStrategy):
    """Horizontal area of a single Polygon. Holes are subtracted by Shapely."""

    geometry_type: ClassVar[str] = GeometryType.POLYGON.value

    def measure(self, geometry: BaseGeometry) -> MeasurementValue:
        planar = planar_geometry(geometry)
        if planar is None or planar.geom_type != GeometryType.POLYGON.value:
            return MeasurementValue.invalid()
        area = float(planar.area)
        if not math.isfinite(area):
            return MeasurementValue.invalid()
        return MeasurementValue.completed(
            round(area, _AREA_DECIMALS),
            MeasurementUnit.SQUARE_METRES,
        )
