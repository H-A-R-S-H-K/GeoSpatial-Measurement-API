"""Strategy behaviour for area, length, points, and unknown types."""

import geopandas as gpd
import pytest
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box

from app.core.enums import MeasurementStatus, MeasurementUnit
from app.domain.measurement import MeasurementValue
from app.measurement_strategies.base import MeasurementStrategy
from app.measurement_strategies.line_string import LineStringMeasurementStrategy
from app.measurement_strategies.point import PointMeasurementStrategy
from app.measurement_strategies.polygon import PolygonMeasurementStrategy
from app.measurement_strategies.registry import MeasurementStrategyRegistry
from app.readers.feature_mapper import extract_features
from app.services.measurement_service import MeasurementService

_TOLERANCE = 1e-6


def test_polygon_area_includes_holes() -> None:
    outer = box(0, 0, 100, 100)
    hole = box(10, 10, 30, 30)
    polygon = Polygon(outer.exterior.coords, [list(hole.exterior.coords)])

    result = PolygonMeasurementStrategy().measure(polygon)

    assert result.status is MeasurementStatus.COMPLETED
    assert result.unit is MeasurementUnit.SQUARE_METRES
    assert result.measurement is not None
    assert abs(result.measurement - 9_600) < _TOLERANCE


def test_linestring_length() -> None:
    result = LineStringMeasurementStrategy().measure(LineString([(0, 0), (3, 4)]))

    assert result.status is MeasurementStatus.COMPLETED
    assert result.unit is MeasurementUnit.METRES
    assert result.measurement is not None
    assert abs(result.measurement - 5) < _TOLERANCE


def test_linestring_length_ignores_altitude() -> None:
    result = LineStringMeasurementStrategy().measure(LineString([(0, 0, 0), (3, 4, 12)]))

    assert result.measurement is not None
    assert abs(result.measurement - 5) < _TOLERANCE


def test_point_has_no_measurement() -> None:
    result = PointMeasurementStrategy().measure(Point(12, 77))

    assert result.status is MeasurementStatus.NOT_REQUIRED
    assert result.measurement is None
    assert result.unit is None


def test_invalid_polygon_is_not_repaired() -> None:
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    assert bowtie.is_valid is False

    result = PolygonMeasurementStrategy().measure(bowtie)

    assert result.status is MeasurementStatus.INVALID_GEOMETRY
    assert result.measurement is None


def test_empty_polygon_is_invalid() -> None:
    result = PolygonMeasurementStrategy().measure(Polygon())

    assert result.status is MeasurementStatus.INVALID_GEOMETRY


def test_unsupported_geometry_does_not_raise() -> None:
    frame = gpd.GeoDataFrame(
        geometry=[MultiPolygon([box(0, 0, 1, 1), box(2, 2, 3, 3)])],
        crs="EPSG:32643",
    )
    service = MeasurementService(MeasurementStrategyRegistry.with_defaults())

    results = service.measure(extract_features(frame))

    assert results[0].geometry_type == "MultiPolygon"
    assert results[0].status is MeasurementStatus.UNSUPPORTED_GEOMETRY
    assert results[0].measurement is None
    assert results[0].unit is None


def test_null_geometry_is_invalid_and_does_not_raise() -> None:
    frame = gpd.GeoDataFrame({"name": ["missing"]}, geometry=[None], crs="EPSG:32643")
    service = MeasurementService(MeasurementStrategyRegistry.with_defaults())

    results = service.measure(extract_features(frame))

    assert results[0].status is MeasurementStatus.INVALID_GEOMETRY
    assert results[0].properties["name"] == "missing"


def test_new_strategy_is_used_without_changing_the_service() -> None:
    class MultiPolygonArea(MeasurementStrategy):
        """Stand-in for a geometry type the default registry does not know."""

        geometry_type = "MultiPolygon"

        def measure(self, geometry: MultiPolygon) -> MeasurementValue:
            return MeasurementValue.completed(float(geometry.area), MeasurementUnit.SQUARE_METRES)

    registry = MeasurementStrategyRegistry()
    registry.register(MultiPolygonArea())
    frame = gpd.GeoDataFrame(
        geometry=[MultiPolygon([box(0, 0, 2, 2)])],
        crs="EPSG:32643",
    )

    results = MeasurementService(registry).measure(extract_features(frame))

    assert results[0].status is MeasurementStatus.COMPLETED
    assert results[0].measurement == pytest.approx(4)
