"""Reader and reader-factory tests."""

import zipfile
from pathlib import Path

import geopandas as gpd
import pytest

from app.core.exceptions import InvalidGeospatialFileError, UnsupportedFileFormatError
from app.readers.base import GeospatialReader
from app.readers.factory import ReaderFactory, ReaderRegistration, default_registrations
from app.readers.kml_reader import KMLReader
from app.readers.shapefile_reader import ShapefileReader
from tests.helpers import build_kml, local_sample, write_shapefile_zip


def test_kml_reader_returns_features_and_wgs84_crs(tmp_path: Path) -> None:
    sample = local_sample(77.2, 28.6)
    path = tmp_path / "survey.kml"
    path.write_bytes(build_kml([("square", sample.geographic.geometry.iloc[0])]))

    frame = KMLReader().read(path)

    assert len(frame) == 1
    assert frame.geometry.iloc[0].geom_type == "Polygon"
    assert frame.crs is not None
    assert frame.crs.to_epsg() == 4326
    assert "square" in " ".join(str(value) for value in frame.iloc[0].tolist()).lower()


def test_kml_reader_rejects_malformed_xml(tmp_path: Path) -> None:
    path = tmp_path / "broken.kml"
    path.write_bytes(b"<not-kml>")

    with pytest.raises(InvalidGeospatialFileError, match="could not be parsed"):
        KMLReader().read(path)


def test_shapefile_reader_round_trips_a_zip(tmp_path: Path) -> None:
    sample = local_sample(77.2, 28.6)
    archive = tmp_path / "layer.zip"
    write_shapefile_zip(archive, sample.projected.iloc[[0]])

    frame = ShapefileReader(max_entries=32, max_uncompressed_bytes=1_000_000).read(archive)

    assert len(frame) == 1
    assert frame.geometry.iloc[0].geom_type == "Polygon"
    assert frame.crs is not None
    assert frame.crs.to_epsg() == sample.utm_epsg


def test_shapefile_reader_reports_a_missing_component(tmp_path: Path) -> None:
    sample = local_sample(77.2, 28.6)
    archive = tmp_path / "layer.zip"
    write_shapefile_zip(archive, sample.projected.iloc[[0]])
    without_dbf = tmp_path / "nodbf.zip"
    _rewrite_zip_without(archive, without_dbf, ".dbf")

    with pytest.raises(InvalidGeospatialFileError, match=r"\.dbf"):
        ShapefileReader(max_entries=32, max_uncompressed_bytes=1_000_000).read(without_dbf)


def test_shapefile_without_prj_has_no_crs(tmp_path: Path) -> None:
    sample = local_sample(77.2, 28.6)
    archive = tmp_path / "noprj.zip"
    write_shapefile_zip(archive, sample.projected.iloc[[0]], include_prj=False)

    frame = ShapefileReader(max_entries=32, max_uncompressed_bytes=1_000_000).read(archive)

    assert frame.crs is None


def test_shapefile_reader_rejects_a_zip_that_is_not_a_shapefile(tmp_path: Path) -> None:
    archive = tmp_path / "notes.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("readme.txt", b"hello")

    with pytest.raises(InvalidGeospatialFileError, match="does not contain a Shapefile"):
        ShapefileReader(max_entries=32, max_uncompressed_bytes=1_000_000).read(archive)


def test_shapefile_reader_rejects_multiple_shapefiles(tmp_path: Path) -> None:
    sample = local_sample(77.2, 28.6)
    first = tmp_path / "one.zip"
    second = tmp_path / "two.zip"
    write_shapefile_zip(first, sample.projected.iloc[[0]])
    write_shapefile_zip(second, sample.projected.iloc[[0]])
    combined = tmp_path / "both.zip"
    with (
        zipfile.ZipFile(combined, "w") as archive,
        zipfile.ZipFile(first) as left,
        zipfile.ZipFile(second) as right,
    ):
        for info in left.infolist():
            archive.writestr(f"a/{info.filename}", left.read(info))
        for info in right.infolist():
            archive.writestr(f"b/{info.filename}", right.read(info))

    with pytest.raises(InvalidGeospatialFileError, match="multiple Shapefiles"):
        ShapefileReader(max_entries=32, max_uncompressed_bytes=1_000_000).read(combined)


def test_malformed_zip_is_rejected(tmp_path: Path) -> None:
    archive = tmp_path / "broken.zip"
    archive.write_bytes(b"this is not a zip")

    with pytest.raises(InvalidGeospatialFileError, match="not a valid ZIP"):
        ShapefileReader(max_entries=32, max_uncompressed_bytes=1_000_000).read(archive)


def test_factory_selects_reader_by_extension() -> None:
    from app.core.config import Settings

    factory = ReaderFactory(default_registrations(Settings(temp_dir=None)))

    assert isinstance(factory.create(Path("survey.kml")), KMLReader)
    assert isinstance(factory.create(Path("survey.ZIP")), ShapefileReader)
    assert factory.supports_extension(".kml")
    assert not factory.supports_extension(".geojson")
    with pytest.raises(UnsupportedFileFormatError):
        factory.create(Path("city.geojson"))


def test_factory_accepts_a_new_reader_without_changing_existing_ones() -> None:
    class GeoJSONReader(GeospatialReader):
        extensions = frozenset({".geojson"})

        def read(self, path: Path) -> gpd.GeoDataFrame:
            raise NotImplementedError

    factory = ReaderFactory([ReaderRegistration(GeoJSONReader, GeoJSONReader)])

    assert factory.supports_extension(".geojson")
    assert isinstance(factory.create(Path("city.geojson")), GeoJSONReader)


def _rewrite_zip_without(source: Path, target: Path, suffix: str) -> None:
    with zipfile.ZipFile(source) as incoming, zipfile.ZipFile(target, "w") as outgoing:
        for info in incoming.infolist():
            if Path(info.filename).suffix.lower() == suffix:
                continue
            outgoing.writestr(info, incoming.read(info))
