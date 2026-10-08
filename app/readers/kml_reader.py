"""Read KML into a GeoDataFrame.

KML coordinates are longitude/latitude in WGS 84. When the driver omits a CRS,
this reader assigns EPSG:4326 because that is what the KML specification requires.
Shapefiles do not get the same default: a missing ``.prj`` stays missing and is
rejected later by ``CRSService``.
"""

import logging
from pathlib import Path
from typing import ClassVar

import geopandas as gpd
import pandas as pd

from app.core.exceptions import InvalidGeospatialFileError
from app.readers.base import GeospatialReader, normalize_geodataframe

logger = logging.getLogger(__name__)

KML_DEFAULT_CRS = "EPSG:4326"


class KMLReader(GeospatialReader):
    """Read every layer of a KML file and concatenate the features."""

    extensions: ClassVar[frozenset[str]] = frozenset({".kml"})

    def read(self, path: Path) -> gpd.GeoDataFrame:
        frames = _read_layers(path)
        return _combine(frames)


def _read_layers(path: Path) -> list[gpd.GeoDataFrame]:
    layer_names = _layer_names(path)
    if layer_names:
        try:
            return [gpd.read_file(path, layer=name) for name in layer_names]
        except Exception as exc:
            logger.debug(
                "Layered KML read failed for %s, retrying as one layer: %s",
                path.name,
                exc,
            )
    try:
        return [gpd.read_file(path)]
    except Exception as exc:
        logger.warning("KML parse failed for %s: %s", path.name, exc)
        raise InvalidGeospatialFileError("The KML file could not be parsed.") from exc


def _layer_names(path: Path) -> list[str]:
    try:
        import pyogrio

        layers = pyogrio.list_layers(path)
    except Exception as exc:
        logger.debug("Could not list KML layers for %s: %s", path.name, exc)
        return []
    names: list[str] = []
    for layer in layers:
        name = str(layer[0]).strip()
        if name:
            names.append(name)
    return names


def _combine(frames: list[gpd.GeoDataFrame]) -> gpd.GeoDataFrame:
    normalized: list[gpd.GeoDataFrame] = []
    for frame in frames:
        if not isinstance(frame, gpd.GeoDataFrame):
            continue
        try:
            normalized.append(normalize_geodataframe(frame))
        except InvalidGeospatialFileError:
            logger.debug("Skipping a KML layer that has no geometry column")
    if not normalized:
        raise InvalidGeospatialFileError("The KML file does not contain a geometry column.")
    crs = next((frame.crs for frame in normalized if frame.crs is not None), None)
    combined = gpd.GeoDataFrame(
        pd.concat(normalized, ignore_index=True),
        geometry="geometry",
        crs=crs,
    )
    if combined.crs is None:
        combined = combined.set_crs(KML_DEFAULT_CRS)
    return combined
