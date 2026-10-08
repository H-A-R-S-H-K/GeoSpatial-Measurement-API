"""Reader contract and shared GeoDataFrame normalization."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

import geopandas as gpd

from app.core.exceptions import InvalidGeospatialFileError


class GeospatialReader(ABC):
    """Parse one geospatial format into a GeoDataFrame.

    A new format implements this class and is registered with ``ReaderFactory``.
    ``FileService`` does not change.
    """

    extensions: ClassVar[frozenset[str]]

    @abstractmethod
    def read(self, path: Path) -> gpd.GeoDataFrame:
        """Return features, attribute columns, and the dataset CRS."""


def normalize_geodataframe(
    frame: gpd.GeoDataFrame,
    *,
    default_crs: str | None = None,
) -> gpd.GeoDataFrame:
    """Copy a frame, name the geometry column ``geometry``, and optionally fill a missing CRS."""
    if not isinstance(frame, gpd.GeoDataFrame) or frame.geometry.name not in frame.columns:
        raise InvalidGeospatialFileError("The dataset does not contain a geometry column.")
    result = frame.copy()
    if result.geometry.name != "geometry":
        result = result.rename_geometry("geometry")
    if result.crs is None and default_crs is not None:
        result = result.set_crs(default_crs)
    return result
