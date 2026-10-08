"""Choose a metre-based CRS and transform the dataset when that is required.

Geographic coordinates such as EPSG:4326 are longitude and latitude in degrees.
Polygon area and line length computed directly in that CRS are angular, not
square metres or metres, and they change meaning with latitude. This service
therefore refuses to hand a geographic frame to the measurement step when the
frame actually has geometry to measure.

Selection rules:

1. A missing CRS is an error.
2. A projected CRS whose axes are already metres is used unchanged.
3. Otherwise GeoPandas estimates a local UTM CRS from the dataset centroid
   and transforms the frame with ``to_crs``. No zone is hard-coded, and this
   module does not implement projection mathematics.
4. Polar data is rejected because UTM is not an appropriate projection there.
5. A dataset with no finite bounds is returned unchanged: there is nothing to measure.

UTM is a local approximation. A dataset wider than one zone is still transformed
into the zone of its centroid, and a warning is logged. Web Mercator
(EPSG:3857) is metres, so rule 2 keeps it, even though its distances are distorted.
"""

import logging
import math
from dataclasses import dataclass

import geopandas as gpd
from pyproj import CRS

from app.core.exceptions import CRSTransformationError, MissingCRSError

logger = logging.getLogger(__name__)

_METRE_UNIT_NAMES = frozenset({"m", "meter", "metre", "meters", "metres"})
_POLAR_SOUTH_DEGREES = -80.0
_POLAR_NORTH_DEGREES = 84.0
_UTM_ZONE_WIDTH_DEGREES = 6.0


@dataclass(frozen=True)
class PreparedDataset:
    """A frame that is safe to measure, plus the CRS labels to persist."""

    geodataframe: gpd.GeoDataFrame
    original_crs: str
    measurement_crs: str
    transformed: bool


class CRSService:
    """Validate the dataset CRS and return a frame whose units are metres."""

    def prepare(self, frame: gpd.GeoDataFrame) -> PreparedDataset:
        crs = frame.crs
        if crs is None:
            raise MissingCRSError("The dataset does not define a coordinate reference system.")
        original = format_crs(crs)
        if uses_metre_units(crs):
            return PreparedDataset(
                geodataframe=frame,
                original_crs=original,
                measurement_crs=original,
                transformed=False,
            )
        if not _has_finite_bounds(frame):
            return PreparedDataset(
                geodataframe=frame,
                original_crs=original,
                measurement_crs=original,
                transformed=False,
            )
        if crs.is_geographic:
            _reject_polar(frame)
            _warn_if_wider_than_one_utm_zone(frame)
        projected = _transform_to_estimated_utm(frame)
        measurement_crs = projected.crs
        if measurement_crs is None or not uses_metre_units(measurement_crs):
            raise CRSTransformationError(
                "An appropriate metre-based projected CRS could not be determined for this dataset."
            )
        formatted = format_crs(measurement_crs)
        logger.info("Transformed dataset from %s to %s for measurement", original, formatted)
        return PreparedDataset(
            geodataframe=projected,
            original_crs=original,
            measurement_crs=formatted,
            transformed=True,
        )


def format_crs(crs: CRS) -> str:
    """Prefer an authority code such as ``EPSG:4326`` over a long WKT string."""
    authority = crs.to_authority()
    if authority is not None:
        return f"{authority[0]}:{authority[1]}"
    epsg = crs.to_epsg()
    if epsg is not None:
        return f"EPSG:{epsg}"
    return crs.to_string()


def uses_metre_units(crs: CRS) -> bool:
    """True when every axis is a projected metre axis."""
    if not crs.is_projected:
        return False
    axes = list(crs.axis_info)
    if not axes:
        return False
    return all(axis.unit_name.casefold() in _METRE_UNIT_NAMES for axis in axes)


def _has_finite_bounds(frame: gpd.GeoDataFrame) -> bool:
    if frame.empty:
        return False
    try:
        bounds = frame.total_bounds
    except Exception:
        return False
    return all(math.isfinite(float(value)) for value in bounds)


def _reject_polar(frame: gpd.GeoDataFrame) -> None:
    _min_x, min_y, _max_x, max_y = frame.total_bounds
    if float(min_y) < _POLAR_SOUTH_DEGREES or float(max_y) > _POLAR_NORTH_DEGREES:
        raise CRSTransformationError(
            "The dataset extends into polar latitudes, where a UTM projection is not appropriate."
        )


def _warn_if_wider_than_one_utm_zone(frame: gpd.GeoDataFrame) -> None:
    min_x, _min_y, max_x, _max_y = frame.total_bounds
    width = float(max_x - min_x)
    if width > _UTM_ZONE_WIDTH_DEGREES:
        logger.warning(
            "Dataset longitude span is %.2f degrees, which is wider than one UTM zone. "
            "Measurements use the UTM zone of the dataset centroid and can be distorted.",
            width,
        )


def _transform_to_estimated_utm(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    try:
        estimated = frame.estimate_utm_crs()
        return frame.to_crs(estimated)
    except CRSTransformationError:
        raise
    except Exception as exc:
        logger.warning("UTM estimation failed: %s", exc)
        raise CRSTransformationError(
            "An appropriate metre-based projected CRS could not be determined for this dataset."
        ) from exc
