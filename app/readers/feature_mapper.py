"""Turn a GeoDataFrame into plain feature objects for the measurement step."""

import math
from datetime import date, datetime
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from app.core.exceptions import InvalidGeospatialFileError
from app.domain.feature import GeospatialFeature


def extract_features(frame: gpd.GeoDataFrame) -> list[GeospatialFeature]:
    """Preserve feature order, geometry type, geometry, and attribute columns."""
    if frame.geometry.name not in frame.columns:
        raise InvalidGeospatialFileError("The dataset does not contain a geometry column.")
    normalized = frame.reset_index(drop=True)
    geometries = normalized.geometry.tolist()
    attributes = normalized.drop(columns=normalized.geometry.name)
    # A geometry-only frame has no columns left. pandas then returns no records at all.
    records: list[dict[str, Any]]
    if len(attributes.columns) == 0:
        records = [{} for _ in geometries]
    else:
        records = [
            {str(key): value for key, value in row.items()}
            for row in attributes.to_dict(orient="records")
        ]
    features: list[GeospatialFeature] = []
    for feature_id, (geometry, properties) in enumerate(zip(geometries, records, strict=True)):
        geom = geometry if isinstance(geometry, BaseGeometry) else None
        features.append(
            GeospatialFeature(
                feature_id=feature_id,
                geometry_type=None if geom is None else geom.geom_type,
                geometry=geom,
                properties={str(key): to_jsonable(value) for key, value in properties.items()},
            )
        )
    return features


def to_jsonable(value: Any) -> Any:
    """Convert driver-specific attribute values into JSON-safe Python values."""
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, BaseGeometry):
        return mapping(value)
    if isinstance(value, np.generic):
        return to_jsonable(value.item())
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(item) for item in value]
    try:
        if bool(pd.isna(value)):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)
