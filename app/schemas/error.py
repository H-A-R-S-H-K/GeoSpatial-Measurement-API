"""Error body returned for expected failures."""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Machine-readable error. Stack traces are never included."""

    error: str = Field(description="Stable error code.")
    message: str = Field(description="What the client can do about the failure.")
    file_id: str | None = Field(
        default=None,
        description="Persisted file id when a record was stored before the failure.",
    )
