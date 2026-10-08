"""HTTP contract: upload, lookup, measurements, and error codes."""

from pathlib import Path

import geopandas as gpd
from fastapi.testclient import TestClient
from shapely.geometry import MultiPolygon, box

from app.core.config import Settings
from app.main import create_app
from tests.helpers import build_kml, local_sample, write_shapefile_zip

_AREA_TOLERANCE_M2 = 1.0


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_kml_then_read_file_and_measurements(client: TestClient) -> None:
    sample = local_sample(77.2, 28.6)
    polygon = sample.geographic.geometry.iloc[0]
    line = sample.geographic.geometry.iloc[1]
    point = sample.geographic.geometry.iloc[2]
    content = build_kml([("square", polygon), ("path", line), ("marker", point)])

    created = client.post(
        "/api/files/",
        files={"file": ("survey.kml", content, "application/vnd.google-earth.kml+xml")},
    )

    assert created.status_code == 201
    body = created.json()
    assert body["filename"] == "survey.kml"
    assert body["feature_count"] == 3
    assert body["crs"] == "EPSG:4326"
    assert body["measurement_crs"] == f"EPSG:{sample.utm_epsg}"
    assert body["status"] == "COMPLETED"
    assert body["error_message"] is None

    fetched = client.get(f"/api/files/{body['id']}/")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]
    assert fetched.json()["feature_count"] == 3

    measurements = client.get(f"/api/files/{body['id']}/measurements/")
    assert measurements.status_code == 200
    rows = measurements.json()["measurements"]
    assert [row["feature_id"] for row in rows] == [0, 1, 2]
    by_type = {row["geometry_type"]: row for row in rows}
    assert by_type["Polygon"]["status"] == "COMPLETED"
    assert by_type["Polygon"]["unit"] == "m²"
    assert abs(by_type["Polygon"]["measurement"] - sample.square_area_m2) < _AREA_TOLERANCE_M2
    assert by_type["LineString"]["status"] == "COMPLETED"
    assert by_type["LineString"]["unit"] == "m"
    assert abs(by_type["LineString"]["measurement"] - sample.line_length_m) < 1.0
    assert by_type["Point"]["status"] == "NOT_REQUIRED"
    assert by_type["Point"]["measurement"] is None
    assert by_type["Point"]["unit"] is None
    assert "square" in str(by_type["Polygon"]["properties"]).lower()


def test_upload_shapefile_zip(client: TestClient, tmp_path: Path) -> None:
    sample = local_sample(77.2, 28.6)
    archive = tmp_path / "layer.zip"
    write_shapefile_zip(archive, sample.projected.iloc[[0]])

    response = client.post(
        "/api/files/",
        files={"file": ("parcels.zip", archive.read_bytes(), "application/zip")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["crs"] == f"EPSG:{sample.utm_epsg}"
    assert body["measurement_crs"] == body["crs"]
    rows = client.get(f"/api/files/{body['id']}/measurements/").json()["measurements"]
    assert abs(rows[0]["measurement"] - sample.square_area_m2) < _AREA_TOLERANCE_M2


def test_unsupported_extension(client: TestClient) -> None:
    response = client.post(
        "/api/files/",
        files={"file": ("city.geojson", b"{}", "application/geo+json")},
    )

    assert response.status_code == 400
    assert response.json()["error"] == "UNSUPPORTED_FILE_FORMAT"
    assert "file_id" not in response.json()


def test_malformed_kml_returns_422_and_can_be_fetched(client: TestClient) -> None:
    response = client.post(
        "/api/files/",
        files={"file": ("broken.kml", b"this is not kml", "application/xml")},
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "INVALID_GEOSPATIAL_FILE"
    file_id = payload["file_id"]

    fetched = client.get(f"/api/files/{file_id}/")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "FAILED"
    assert fetched.json()["error_message"]

    measurements = client.get(f"/api/files/{file_id}/measurements/")
    assert measurements.status_code == 200
    assert measurements.json()["measurements"] == []


def test_missing_shapefile_crs(client: TestClient, tmp_path: Path) -> None:
    sample = local_sample(77.2, 28.6)
    archive = tmp_path / "noprj.zip"
    write_shapefile_zip(archive, sample.projected.iloc[[0]], include_prj=False)

    response = client.post(
        "/api/files/",
        files={"file": ("noprj.zip", archive.read_bytes(), "application/zip")},
    )

    assert response.status_code == 422
    assert response.json()["error"] == "MISSING_CRS"
    fetched = client.get(f"/api/files/{response.json()['file_id']}/")
    assert fetched.json()["status"] == "FAILED"


def test_unknown_file_is_404(client: TestClient) -> None:
    missing = client.get("/api/files/does-not-exist/")
    assert missing.status_code == 404
    assert missing.json()["error"] == "FILE_NOT_FOUND"

    measurements = client.get("/api/files/does-not-exist/measurements/")
    assert measurements.status_code == 404
    assert measurements.json()["error"] == "FILE_NOT_FOUND"


def test_multipolygon_does_not_fail_the_upload(client: TestClient, tmp_path: Path) -> None:
    frame = gpd.GeoDataFrame(
        geometry=[MultiPolygon([box(0, 0, 10, 10), box(20, 20, 25, 25)])],
        crs="EPSG:32643",
    )
    archive = tmp_path / "multi.zip"
    write_shapefile_zip(archive, frame)

    response = client.post(
        "/api/files/",
        files={"file": ("multi.zip", archive.read_bytes(), "application/zip")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED"
    rows = client.get(f"/api/files/{body['id']}/measurements/").json()["measurements"]
    assert rows[0]["geometry_type"] == "MultiPolygon"
    assert rows[0]["status"] == "UNSUPPORTED_GEOMETRY"
    assert rows[0]["measurement"] is None
    assert rows[0]["unit"] is None


def test_upload_over_the_size_limit(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        temp_dir=str(tmp_path / "tmp"),
        max_upload_bytes=32,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/files/",
            files={"file": ("a.kml", b"x" * 64, "application/xml")},
        )

    assert response.status_code == 413
    assert response.json()["error"] == "FILE_TOO_LARGE"


def test_missing_file_field_is_a_validation_error(client: TestClient) -> None:
    response = client.post("/api/files/")

    assert response.status_code == 422
