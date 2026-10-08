"""Read and insert feature measurements."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.measurement import FeatureMeasurement
from app.models.measurement import MeasurementRecord


class MeasurementRepository:
    """Persistence for ``measurements``. Does not commit the session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_all(self, file_id: str, measurements: Sequence[FeatureMeasurement]) -> None:
        self._session.add_all(
            [
                MeasurementRecord(
                    file_id=file_id,
                    feature_index=item.feature_id,
                    geometry_type=item.geometry_type,
                    measurement=item.measurement,
                    unit=item.unit.value if item.unit is not None else None,
                    status=item.status.value,
                    properties=item.properties,
                )
                for item in measurements
            ]
        )
        self._session.flush()

    def list_for_file(self, file_id: str) -> list[MeasurementRecord]:
        statement = (
            select(MeasurementRecord)
            .where(MeasurementRecord.file_id == file_id)
            .order_by(MeasurementRecord.feature_index.asc())
        )
        return list(self._session.scalars(statement).all())
