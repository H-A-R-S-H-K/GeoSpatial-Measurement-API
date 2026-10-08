"""CRS selection: project geographic data, and leave metre data alone."""

import logging

import geopandas as gpd
import pytest
from shapely.geometry import Point, box

from app.core.exceptions import CRSTransformationError, MissingCRSError
from app.services.crs_service import CRSService, uses_metre_units
from tests.helpers import local_sample

_AREA_TOLERANCE_M2 = 1.0


def test_epsg_4326_is_projected_before_area_is_meaningful() -> None:
    sample = local_sample(77.2, 28.6)
    geographic = sample.geographic.iloc[[0]].copy()
    degree_area = float(geographic.geometry.iloc[0].area)

    prepared = CRSService().prepare(geographic)

    assert prepared.transformed is True
    assert prepared.original_crs == "EPSG:4326"
    assert prepared.measurement_crs == f"EPSG:{sample.utm_epsg}"
    assert sample.utm_epsg == 32643
    measured_area = float(prepared.geodataframe.geometry.iloc[0].area)
    assert abs(measured_area - sample.square_area_m2) < _AREA_TOLERANCE_M2
    assert abs(measured_area - degree_area) > 1_000


def test_southern_hemisphere_selects_a_southern_utm_zone() -> None:
    sample = local_sample(151.2, -33.8)
    prepared = CRSService().prepare(sample.geographic.iloc[[0]].copy())

    assert sample.utm_epsg == 32756
    assert prepared.measurement_crs == "EPSG:32756"
    measured_area = float(prepared.geodataframe.geometry.iloc[0].area)
    assert abs(measured_area - sample.square_area_m2) < _AREA_TOLERANCE_M2


def test_metre_projected_crs_is_not_transformed() -> None:
    sample = local_sample(77.2, 28.6)
    frame = sample.projected.iloc[[0]].copy()
    before = frame.geometry.iloc[0].wkt

    prepared = CRSService().prepare(frame)

    assert prepared.transformed is False
    assert prepared.original_crs == f"EPSG:{sample.utm_epsg}"
    assert prepared.measurement_crs == prepared.original_crs
    assert prepared.geodataframe.geometry.iloc[0].wkt == before


def test_web_mercator_is_kept_because_its_axes_are_metres() -> None:
    origin = gpd.GeoSeries([Point(77.2, 28.6)], crs="EPSG:4326").to_crs("EPSG:3857")
    x = float(origin.iloc[0].x)
    y = float(origin.iloc[0].y)
    frame = gpd.GeoDataFrame(geometry=[box(x, y, x + 100, y + 100)], crs="EPSG:3857")
    before = frame.geometry.iloc[0].wkt

    prepared = CRSService().prepare(frame)

    assert prepared.transformed is False
    assert prepared.measurement_crs == "EPSG:3857"
    assert prepared.geodataframe.geometry.iloc[0].wkt == before


def test_projected_foot_crs_is_transformed_to_metres() -> None:
    origin = gpd.GeoSeries([Point(-74.0, 40.7)], crs="EPSG:4326").to_crs("EPSG:2263")
    x = float(origin.iloc[0].x)
    y = float(origin.iloc[0].y)
    frame = gpd.GeoDataFrame(geometry=[box(x, y, x + 500, y + 500)], crs="EPSG:2263")

    prepared = CRSService().prepare(frame)

    assert prepared.transformed is True
    assert prepared.original_crs == "EPSG:2263"
    assert prepared.measurement_crs != "EPSG:2263"
    assert uses_metre_units(prepared.geodataframe.crs)


def test_missing_crs_is_rejected() -> None:
    frame = gpd.GeoDataFrame(geometry=[box(0, 0, 1, 1)])

    with pytest.raises(MissingCRSError):
        CRSService().prepare(frame)


def test_polar_data_is_not_forced_into_utm() -> None:
    frame = gpd.GeoDataFrame(geometry=[box(0, 85, 1, 86)], crs="EPSG:4326")

    with pytest.raises(CRSTransformationError, match="polar"):
        CRSService().prepare(frame)


def test_dataset_wider_than_one_utm_zone_warns_and_still_projects(
    caplog: pytest.LogCaptureFixture,
) -> None:
    frame = gpd.GeoDataFrame(geometry=[box(0, 10, 20, 12)], crs="EPSG:4326")

    with caplog.at_level(logging.WARNING, logger="app.services.crs_service"):
        prepared = CRSService().prepare(frame)

    assert prepared.transformed is True
    assert uses_metre_units(prepared.geodataframe.crs)
    assert "wider than one UTM zone" in caplog.text


def test_empty_dataset_with_a_crs_is_not_transformed() -> None:
    frame = gpd.GeoDataFrame(geometry=gpd.GeoSeries([], crs="EPSG:4326"))

    prepared = CRSService().prepare(frame)

    assert prepared.transformed is False
    assert prepared.original_crs == "EPSG:4326"
    assert prepared.measurement_crs == "EPSG:4326"
