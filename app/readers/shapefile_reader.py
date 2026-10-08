"""Read a Shapefile packaged as a ZIP archive."""

import logging
import tempfile
from pathlib import Path
from typing import ClassVar

import geopandas as gpd

from app.core.exceptions import InvalidGeospatialFileError
from app.readers.base import GeospatialReader, normalize_geodataframe
from app.utils.file_utils import safe_extract_zip

logger = logging.getLogger(__name__)

_JUNK_DIRECTORIES = {"__MACOSX"}
_REQUIRED_COMPONENTS = (".shp", ".shx", ".dbf")


class ShapefileReader(GeospatialReader):
    """Extract one zipped Shapefile and load it with GeoPandas.

    ``.shp``, ``.shx``, and ``.dbf`` are required. ``.prj`` is optional here;
    a missing CRS is reported by ``CRSService`` rather than as a bad archive.
    """

    extensions: ClassVar[frozenset[str]] = frozenset({".zip"})

    def __init__(self, *, max_entries: int, max_uncompressed_bytes: int) -> None:
        self._max_entries = max_entries
        self._max_uncompressed_bytes = max_uncompressed_bytes

    def read(self, path: Path) -> gpd.GeoDataFrame:
        with tempfile.TemporaryDirectory(prefix="shapefile-") as directory:
            destination = Path(directory)
            safe_extract_zip(
                path,
                destination,
                max_entries=self._max_entries,
                max_uncompressed_bytes=self._max_uncompressed_bytes,
            )
            shapefile = _locate_shapefile(destination)
            try:
                loaded = gpd.read_file(shapefile)
            except Exception as exc:
                logger.warning("Shapefile parse failed for %s: %s", path.name, exc)
                raise InvalidGeospatialFileError("The Shapefile could not be parsed.") from exc
            # Copy while the extracted files still exist so the frame does not
            # depend on the temporary directory that is about to be deleted.
            return normalize_geodataframe(loaded).copy()


def _locate_shapefile(root: Path) -> Path:
    candidates = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() == ".shp" and not _is_junk(path)
    ]
    if not candidates:
        raise InvalidGeospatialFileError("ZIP archive does not contain a Shapefile (.shp).")
    if len(candidates) > 1:
        raise InvalidGeospatialFileError(
            "ZIP archive contains multiple Shapefiles. Upload one dataset at a time."
        )
    shapefile = _normalize_component_names(candidates[0])
    present = {
        sibling.suffix.lower()
        for sibling in shapefile.parent.iterdir()
        if sibling.is_file() and sibling.stem == shapefile.stem
    }
    missing = [extension for extension in _REQUIRED_COMPONENTS if extension not in present]
    if missing:
        raise InvalidGeospatialFileError(
            "Shapefile is missing required component(s): " + ", ".join(missing) + "."
        )
    return shapefile


def _is_junk(path: Path) -> bool:
    return path.name.startswith("._") or any(part in _JUNK_DIRECTORIES for part in path.parts)


def _normalize_component_names(shapefile: Path) -> Path:
    """Match sidecar names to the ``.shp`` stem so lookup is not case-sensitive."""
    stem = shapefile.stem
    for sibling in list(shapefile.parent.iterdir()):
        if not sibling.is_file() or sibling.stem.lower() != stem.lower():
            continue
        target = sibling.with_name(f"{stem}{sibling.suffix.lower()}")
        if sibling != target:
            sibling.rename(target)
    return shapefile.with_name(f"{stem}.shp")
