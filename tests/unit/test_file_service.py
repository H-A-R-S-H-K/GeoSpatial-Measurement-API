"""FileService orchestration against a real SQLite database."""

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import FileStatus
from app.core.exceptions import (
    InvalidGeospatialFileError,
    MissingCRSError,
    UnsupportedFileFormatError,
)
from app.models.database import Database
from app.models.file import FileRecord
from app.models.measurement import MeasurementRecord
from app.readers.base import GeospatialReader
from app.readers.factory import ReaderFactory, ReaderRegistration
from tests.conftest import make_file_service
from tests.helpers import build_kml, local_sample, write_shapefile_zip

_AREA_TOLERANCE_M2 = 1.0
_LENGTH_TOLERANCE_M = 0.05


def test_kml_upload_persists_metre_measurements(
    session: Session,
    settings: Settings,
    database: Database,
) -> None:
    sample = local_sample(77.2, 28.6)
    polygon = sample.geographic.geometry.iloc[0]
    content = build_kml([("square", polygon)])
    service = make_file_service(session, settings)

    record = service.process_upload("folder/survey.kml", content)

    assert record.status == FileStatus.COMPLETED.value
    assert record.original_filename == "survey.kml"
    assert record.original_crs == "EPSG:4326"
    assert record.measurement_crs == f"EPSG:{sample.utm_epsg}"
    assert record.feature_count == 1
    assert list(settings.resolved_temp_dir.glob("*")) == []

    other = database.session_factory()
    try:
        stored = other.get(FileRecord, record.id)
        assert stored is not None
        assert stored.status == FileStatus.COMPLETED.value
        rows = list(
            other.scalars(
                select(MeasurementRecord)
                .where(MeasurementRecord.file_id == record.id)
                .order_by(MeasurementRecord.feature_index)
            ).all()
        )
    finally:
        other.close()

    assert len(rows) == 1
    assert rows[0].geometry_type == "Polygon"
    assert rows[0].unit == "m²"
    assert rows[0].measurement is not None
    assert abs(rows[0].measurement - sample.square_area_m2) < _AREA_TOLERANCE_M2
    assert abs(rows[0].measurement - float(polygon.area)) > 1_000
    assert "square" in str(rows[0].properties).lower()


def test_zipped_shapefile_in_metres_is_measured_without_changing_crs(
    session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    sample = local_sample(77.2, 28.6)
    archive = tmp_path / "layer.zip"
    write_shapefile_zip(archive, sample.projected.iloc[[0]])
    service = make_file_service(session, settings)

    record = service.process_upload("layer.zip", archive.read_bytes())
    rows = service.get_measurements(record.id)

    assert record.original_crs == f"EPSG:{sample.utm_epsg}"
    assert record.measurement_crs == record.original_crs
    assert rows[0].measurement is not None
    assert abs(rows[0].measurement - sample.square_area_m2) < _AREA_TOLERANCE_M2
    assert list(Path(settings.resolved_temp_dir).glob("*")) == []


def test_mixed_geometries_keep_processing_when_one_feature_is_unsupported(
    session: Session,
    settings: Settings,
) -> None:
    frame = gpd.GeoDataFrame(
        {"name": ["square", "path", "pin", "region", "bowtie"]},
        geometry=[
            box(0, 0, 10, 10),
            LineString([(0, 0), (10, 0)]),
            Point(1, 2),
            MultiPolygon([box(0, 0, 1, 1), box(2, 2, 3, 3)]),
            Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)]),
        ],
        crs="EPSG:32643",
    )

    class MemoryReader(GeospatialReader):
        extensions = frozenset({".kml"})

        def read(self, path: Path) -> gpd.GeoDataFrame:
            del path
            return frame

    service = make_file_service(
        session,
        settings,
        reader_factory=ReaderFactory([ReaderRegistration(MemoryReader, MemoryReader)]),
    )

    record = service.process_upload("mixed.kml", b"ignored by the test reader")
    rows = service.get_measurements(record.id)

    assert record.status == FileStatus.COMPLETED.value
    assert record.feature_count == 5
    assert [row.status for row in rows] == [
        "COMPLETED",
        "COMPLETED",
        "NOT_REQUIRED",
        "UNSUPPORTED_GEOMETRY",
        "INVALID_GEOMETRY",
    ]
    assert rows[0].measurement == pytest.approx(100)
    assert rows[1].measurement == pytest.approx(10)
    assert rows[2].measurement is None
    assert rows[3].measurement is None
    assert rows[3].geometry_type == "MultiPolygon"
    assert rows[4].measurement is None
    assert rows[0].properties["name"] == "square"


def test_malformed_kml_is_persisted_as_failed_and_temp_file_is_removed(
    session: Session,
    settings: Settings,
) -> None:
    service = make_file_service(session, settings)

    with pytest.raises(InvalidGeospatialFileError) as caught:
        service.process_upload("broken.kml", b"<not-kml>")

    assert caught.value.file_id is not None
    stored = service.get_file(caught.value.file_id)
    assert stored.status == FileStatus.FAILED.value
    assert stored.error_message
    assert service.get_measurements(caught.value.file_id) == []
    assert list(Path(settings.resolved_temp_dir).glob("*")) == []


def test_unsupported_extension_is_rejected_without_a_database_row(
    session: Session,
    settings: Settings,
) -> None:
    service = make_file_service(session, settings)

    with pytest.raises(UnsupportedFileFormatError):
        service.process_upload("city.geojson", b"{}")

    assert session.scalar(select(func.count()).select_from(FileRecord)) == 0


def test_shapefile_missing_crs_fails_the_file(
    session: Session,
    settings: Settings,
    tmp_path: Path,
) -> None:
    sample = local_sample(77.2, 28.6)
    archive = tmp_path / "noprj.zip"
    write_shapefile_zip(archive, sample.projected.iloc[[0]], include_prj=False)
    service = make_file_service(session, settings)

    with pytest.raises(MissingCRSError) as caught:
        service.process_upload("noprj.zip", archive.read_bytes())

    assert caught.value.file_id is not None
    stored = service.get_file(caught.value.file_id)
    assert stored.status == FileStatus.FAILED.value
    assert stored.feature_count == 0
