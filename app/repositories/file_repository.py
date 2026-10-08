"""Read and insert file metadata."""

from sqlalchemy.orm import Session

from app.models.file import FileRecord


class FileRepository:
    """Persistence for ``files``. Does not commit the session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, record: FileRecord) -> FileRecord:
        self._session.add(record)
        self._session.flush()
        return record

    def get(self, file_id: str) -> FileRecord | None:
        return self._session.get(FileRecord, file_id)
