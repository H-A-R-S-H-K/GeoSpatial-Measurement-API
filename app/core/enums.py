"""Status, unit, and geometry values shared by the domain and the API."""

from enum import StrEnum


class FileStatus(StrEnum):
    """Lifecycle of one uploaded dataset."""

    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class MeasurementStatus(StrEnum):
    """Outcome of measuring a single feature.

    An unsupported or invalid feature is recorded on its own row. It does not
    fail the rest of the file.
    """

    COMPLETED = "COMPLETED"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNSUPPORTED_GEOMETRY = "UNSUPPORTED_GEOMETRY"
    INVALID_GEOMETRY = "INVALID_GEOMETRY"


class MeasurementUnit(StrEnum):
    """Units produced after coordinates have been projected to metres."""

    SQUARE_METRES = "m²"
    METRES = "m"


class GeometryType(StrEnum):
    """Geometry types this service knows how to measure.

    Shapely's ``geom_type`` uses these same strings. Other types are declined
    by the measurement registry rather than by a conditional chain.
    """

    POLYGON = "Polygon"
    LINE_STRING = "LineString"
    POINT = "Point"
