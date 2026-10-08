"""File upload and measurement lookup.

Handlers validate the request, call ``FileService``, and return a schema.
Parsing, CRS transforms, measurement, and queries stay out of this module.
"""

from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile, status

from app.api.deps import get_file_service
from app.core.config import Settings
from app.schemas.error import ErrorResponse
from app.schemas.file import FileSummary
from app.schemas.measurement import MeasurementItem, MeasurementListResponse
from app.services.file_service import FileService
from app.utils.uploads import read_limited_upload

router = APIRouter(prefix="/files", tags=["files"])

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    413: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


@router.post(
    "/",
    response_model=FileSummary,
    status_code=status.HTTP_201_CREATED,
    responses=_ERROR_RESPONSES,
    summary="Upload a KML file or a zipped Shapefile",
)
async def upload_file(
    request: Request,
    file: UploadFile = File(..., description="A .kml file or a .zip Shapefile."),
    service: FileService = Depends(get_file_service),
) -> FileSummary:
    settings: Settings = request.app.state.settings
    content = await read_limited_upload(file, settings.max_upload_bytes)
    record = service.process_upload(file.filename or "", content)
    return FileSummary.from_record(record)


@router.get(
    "/{file_id}/",
    response_model=FileSummary,
    responses=_ERROR_RESPONSES,
    summary="Fetch metadata for a previously uploaded file",
)
async def get_file(
    file_id: str,
    service: FileService = Depends(get_file_service),
) -> FileSummary:
    return FileSummary.from_record(service.get_file(file_id))


@router.get(
    "/{file_id}/measurements/",
    response_model=MeasurementListResponse,
    responses=_ERROR_RESPONSES,
    summary="Fetch one measurement row per feature",
)
async def get_measurements(
    file_id: str,
    service: FileService = Depends(get_file_service),
) -> MeasurementListResponse:
    rows = service.get_measurements(file_id)
    return MeasurementListResponse(
        file_id=file_id,
        measurements=[MeasurementItem.from_record(row) for row in rows],
    )
