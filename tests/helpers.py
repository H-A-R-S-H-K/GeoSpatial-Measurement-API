"""Small datasets and upload payloads for tests."""

import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import geopandas as gpd
from shapely import force_2d
from shapely.geometry import LineString, Point, box
from shapely.geometry.base import BaseGeometry


@dataclass(frozen=True)
class LocalSample:
    """A square, a line, and a point built in a local UTM zone, plus the WGS 84 copy."""

    projected: gpd.GeoDataFrame
    geographic: gpd.GeoDataFrame
    utm_epsg: int
    square_area_m2: float
    line_length_m: float


def local_sample(
    longitude: float,
    latitude: float,
    *,
    square_size_m: float = 1000.0,
    line_length_m: float = 500.0,
) -> LocalSample:
    """Build geometries in the UTM zone of a point, then also express them as EPSG:4326."""
    origin = gpd.GeoSeries([Point(longitude, latitude)], crs="EPSG:4326")
    utm = origin.estimate_utm_crs()
    projected_origin = origin.to_crs(utm).iloc[0]
    x = float(projected_origin.x)
    y = float(projected_origin.y)
    half = square_size_m / 2
    projected = gpd.GeoDataFrame(
        {"name": ["square", "line", "marker"]},
        geometry=[
            box(x - half, y - half, x + half, y + half),
            LineString([(x, y), (x + line_length_m, y)]),
            Point(x, y),
        ],
        crs=utm,
    )
    epsg = utm.to_epsg()
    if epsg is None:
        raise RuntimeError("Expected the estimated UTM CRS to have an EPSG code.")
    return LocalSample(
        projected=projected,
        geographic=projected.to_crs("EPSG:4326"),
        utm_epsg=int(epsg),
        square_area_m2=square_size_m * square_size_m,
        line_length_m=line_length_m,
    )


def build_kml(features: list[tuple[str, BaseGeometry]]) -> bytes:
    placemarks = [
        f"<Placemark><name>{escape(name)}</name>{_geometry_xml(geometry)}</Placemark>"
        for name, geometry in features
    ]
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
        + "".join(placemarks)
        + "</Document></kml>"
    )
    return document.encode("utf-8")


def write_shapefile_zip(path: Path, frame: gpd.GeoDataFrame, *, include_prj: bool = True) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        frame.to_file(folder / "layer.shp")
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member in sorted(folder.iterdir()):
                if member.suffix.lower() == ".prj" and not include_prj:
                    continue
                archive.write(member, arcname=member.name)


def _geometry_xml(geometry: BaseGeometry) -> str:
    planar = force_2d(geometry)
    if planar.geom_type == "Polygon":
        coordinates = list(planar.exterior.coords)
        body = (
            "<Polygon><outerBoundaryIs><LinearRing><coordinates>"
            f"{_coordinate_text(coordinates)}"
            "</coordinates></LinearRing></outerBoundaryIs></Polygon>"
        )
        return body
    if planar.geom_type == "LineString":
        return (
            "<LineString><coordinates>"
            f"{_coordinate_text(list(planar.coords))}"
            "</coordinates></LineString>"
        )
    if planar.geom_type == "Point":
        return f"<Point><coordinates>{_coordinate_text(list(planar.coords))}</coordinates></Point>"
    raise ValueError(f"Test helper cannot encode {planar.geom_type}.")


def _coordinate_text(coordinates: list[tuple[float, ...]]) -> str:
    return " ".join(f"{x},{y},0" for x, y in coordinates)
