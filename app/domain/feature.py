"""Feature data carried from the reader to the measurement step."""

from dataclasses import dataclass
from typing import Any

from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True)
class GeospatialFeature:
    """One feature extracted from a dataset.

    Geometry stays a Shapely object inside the process. It is not part of the
    API response and it is not written to the database.
    """

    feature_id: int
    geometry_type: str | None
    geometry: BaseGeometry | None
    properties: dict[str, Any]
