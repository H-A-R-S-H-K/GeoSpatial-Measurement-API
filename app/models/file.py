"""Persisted metadata for one uploaded geospatial file."""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base

if TYPE_CHECKING:
    from app.models.measurement import MeasurementRecord


class FileRecord(Base):
    """Upload metadata. Geometry is intentionally not stored."""

    __tablename__ = "files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    feature_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    original_crs: Mapped[str | None] = mapped_column(Text, nullable=True)
    measurement_crs: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    measurements: Mapped[list["MeasurementRecord"]] = relationship(
        back_populates="file",
        cascade="all, delete-orphan",
    )
