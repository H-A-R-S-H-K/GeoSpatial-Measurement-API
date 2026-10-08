"""Apply the registered strategy to each feature.

This service does not know how area or length is calculated. A geometry type
with no strategy becomes ``UNSUPPORTED_GEOMETRY`` and processing continues.
"""

import logging
from collections.abc import Sequence

from app.domain.feature import GeospatialFeature
from app.domain.measurement import FeatureMeasurement, MeasurementValue
from app.measurement_strategies.registry import MeasurementStrategyRegistry

logger = logging.getLogger(__name__)


class MeasurementService:
    """Measure a sequence of features using a strategy registry."""

    def __init__(self, registry: MeasurementStrategyRegistry) -> None:
        self._registry = registry

    def measure(self, features: Sequence[GeospatialFeature]) -> list[FeatureMeasurement]:
        return [self._measure_one(feature) for feature in features]

    def _measure_one(self, feature: GeospatialFeature) -> FeatureMeasurement:
        geometry_type = feature.geometry_type or "Unknown"
        value = self._value_for(feature, geometry_type)
        return FeatureMeasurement(
            feature_id=feature.feature_id,
            geometry_type=geometry_type,
            measurement=value.measurement,
            unit=value.unit,
            status=value.status,
            properties=feature.properties,
        )

    def _value_for(self, feature: GeospatialFeature, geometry_type: str) -> MeasurementValue:
        if feature.geometry is None or feature.geometry_type is None:
            return MeasurementValue.invalid()
        strategy = self._registry.get(geometry_type)
        if strategy is None:
            return MeasurementValue.unsupported()
        try:
            return strategy.measure(feature.geometry)
        except Exception:
            logger.exception("Measurement failed for feature %s", feature.feature_id)
            return MeasurementValue.invalid()
