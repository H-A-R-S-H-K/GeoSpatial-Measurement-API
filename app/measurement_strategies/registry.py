"""Map a geometry type string to the strategy that measures it."""

from app.measurement_strategies.base import MeasurementStrategy
from app.measurement_strategies.line_string import LineStringMeasurementStrategy
from app.measurement_strategies.point import PointMeasurementStrategy
from app.measurement_strategies.polygon import PolygonMeasurementStrategy


class MeasurementStrategyRegistry:
    """Lookup table from Shapely ``geom_type`` to a strategy.

    Types that are not registered are unsupported. The service does not special-case them.
    """

    def __init__(self) -> None:
        self._strategies: dict[str, MeasurementStrategy] = {}

    def register(self, strategy: MeasurementStrategy) -> None:
        self._strategies[strategy.geometry_type] = strategy

    def get(self, geometry_type: str) -> MeasurementStrategy | None:
        return self._strategies.get(geometry_type)

    @classmethod
    def with_defaults(cls) -> "MeasurementStrategyRegistry":
        registry = cls()
        for strategy in (
            PolygonMeasurementStrategy(),
            LineStringMeasurementStrategy(),
            PointMeasurementStrategy(),
        ):
            registry.register(strategy)
        return registry
