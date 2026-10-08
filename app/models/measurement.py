"""Persisted per-feature measurement rows."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base

if TYPE_CHECKING:
    from app.models.file import FileRecord


class MeasurementRecord(Base):
    """One feature's measurement. Attributes are stored; geometry is not."""

    __tablename__ = "measurements"
    __table_args__ = (
        UniqueConstraint("file_id", "feature_index", name="uq_measurements_file_feature"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
    )
    feature_index: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_type: Mapped[str] = mapped_column(String(64), nullable=False)
    measurement: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    file: Mapped["FileRecord"] = relationship(back_populates="measurements")
