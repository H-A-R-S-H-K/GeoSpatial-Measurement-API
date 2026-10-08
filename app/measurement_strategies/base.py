"""Strategy contract and shared geometry checks.

Strategies assume coordinates are already in a metre-based projected CRS.
They do not inspect or transform the dataset CRS.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

import numpy as np
from shapely import force_2d, get_coordinates
from shapely.errors import GEOSException
from shapely.geometry.base import BaseGeometry

from app.domain.measurement import MeasurementValue


class MeasurementStrategy(ABC):
    """Measure one geometry type.

    Register a new subclass for a new type. ``MeasurementService`` looks the
    strategy up and does not grow a branch per geometry.
    """

    geometry_type: ClassVar[str]

    @abstractmethod
    def measure(self, geometry: BaseGeometry) -> MeasurementValue:
        """Return a measurement, or a non-success status when the geometry cannot be used."""


def planar_geometry(geometry: BaseGeometry) -> BaseGeometry | None:
    """Return a valid horizontal geometry, or None when it should not be measured.

    Z values are dropped. Area and length are planimetric measurements in the
    projected plane. Invalid geometries are not repaired: ``buffer(0)`` and
    ``make_valid`` can change the shape and the number the user would see.
    """
    try:
        if not isinstance(geometry, BaseGeometry) or geometry.is_empty or not geometry.is_valid:
            return None
        planar = force_2d(geometry)
        if planar.is_empty or not planar.is_valid:
            return None
        coordinates = get_coordinates(planar)
        if coordinates.size == 0 or not bool(np.isfinite(coordinates).all()):
            return None
    except (GEOSException, TypeError, ValueError):
        return None
    return planar
