"""Errors that are safe to return to API clients."""


class AppError(Exception):
    """Base error translated into a JSON response by the API layer.

    Subclasses set ``code`` and ``status_code``. The message is written for a
    caller who can fix the upload, not for a stack trace.
    """

    code: str = "APPLICATION_ERROR"
    status_code: int = 400

    def __init__(self, message: str, *, file_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.file_id = file_id


class UnsupportedFileFormatError(AppError):
    """The filename extension is not one this service reads."""

    code = "UNSUPPORTED_FILE_FORMAT"
    status_code = 400


class UploadTooLargeError(AppError):
    """The upload exceeds the configured byte limit."""

    code = "FILE_TOO_LARGE"
    status_code = 413


class InvalidGeospatialFileError(AppError):
    """The file has a supported extension but is not a readable dataset."""

    code = "INVALID_GEOSPATIAL_FILE"
    status_code = 422


class MissingCRSError(AppError):
    """The dataset does not declare a coordinate reference system."""

    code = "MISSING_CRS"
    status_code = 422


class CRSTransformationError(AppError):
    """No suitable metre-based projected CRS could be selected."""

    code = "CRS_TRANSFORMATION_FAILED"
    status_code = 422


class StoredFileNotFoundError(AppError):
    """No persisted file matches the requested id."""

    code = "FILE_NOT_FOUND"
    status_code = 404
