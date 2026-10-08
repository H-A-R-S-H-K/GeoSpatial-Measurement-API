"""Safe filenames, temp files, and ZIP extraction."""

import logging
import re
import stat
import zipfile
from pathlib import Path
from typing import IO

from app.core.exceptions import InvalidGeospatialFileError, UnsupportedFileFormatError

logger = logging.getLogger(__name__)

_EXTENSION_RE = re.compile(r"\.[a-z0-9]+")
_MAX_FILENAME_STEM = 200
_COPY_CHUNK_BYTES = 1024 * 1024


def sanitize_filename(filename: str) -> str:
    """Keep the base name and extension. Directory parts are discarded."""
    if not filename or "\x00" in filename:
        raise UnsupportedFileFormatError("Uploaded file must have a filename.")
    name = Path(filename.replace("\\", "/")).name.strip()
    if not name or name in {".", ".."}:
        raise UnsupportedFileFormatError("Uploaded file must have a filename.")
    suffix = Path(name).suffix.lower()
    stem = Path(name).stem.strip() or "upload"
    if len(stem) > _MAX_FILENAME_STEM:
        stem = stem[:_MAX_FILENAME_STEM]
    return f"{stem}{suffix}"


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()


def write_bytes(directory: Path, file_id: str, extension: str, content: bytes) -> Path:
    """Write an upload under a generated id. The original name is never a path segment."""
    if not _EXTENSION_RE.fullmatch(extension):
        raise UnsupportedFileFormatError("Unsupported file extension.")
    directory.mkdir(parents=True, exist_ok=True)
    root = directory.resolve()
    target = (root / f"{file_id}{extension}").resolve()
    if target.parent != root:
        raise UnsupportedFileFormatError("Refusing to store the upload outside the temp directory.")
    target.write_bytes(content)
    return target


def remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove temporary file %s", path.name, exc_info=True)


def safe_extract_zip(
    zip_path: Path,
    destination: Path,
    *,
    max_entries: int,
    max_uncompressed_bytes: int,
) -> None:
    """Extract a ZIP without following member paths outside ``destination``.

    Declared sizes are checked first. Bytes actually copied are capped as well,
    so a header that under-reports the uncompressed size cannot expand without limit.
    Symlink entries are rejected instead of being recreated.
    """
    root = destination.resolve()
    root.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            members = [info for info in archive.infolist() if not info.is_dir()]
            if len(members) > max_entries:
                raise InvalidGeospatialFileError(
                    f"ZIP archive contains {len(members)} files, "
                    f"which exceeds the limit of {max_entries}."
                )
            declared = sum(info.file_size for info in members)
            if declared > max_uncompressed_bytes:
                raise InvalidGeospatialFileError("ZIP archive exceeds the uncompressed size limit.")
            remaining = max_uncompressed_bytes
            for info in members:
                _reject_symlink(info)
                target = _safe_member_path(root, info.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info, "r") as source, target.open("wb") as sink:
                    copied = _copy_limited(source, sink, remaining)
                remaining -= copied
    except zipfile.BadZipFile as exc:
        raise InvalidGeospatialFileError("Uploaded file is not a valid ZIP archive.") from exc


def _reject_symlink(info: zipfile.ZipInfo) -> None:
    mode = info.external_attr >> 16
    if mode and stat.S_ISLNK(mode):
        raise InvalidGeospatialFileError("ZIP archive contains a symlink, which is not allowed.")


def _safe_member_path(root: Path, member_name: str) -> Path:
    normalized = member_name.replace("\\", "/")
    if not normalized or normalized.endswith("/"):
        raise InvalidGeospatialFileError("ZIP archive contains an unsafe path.")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise InvalidGeospatialFileError("ZIP archive contains an absolute path.")
    parts = Path(normalized).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise InvalidGeospatialFileError("ZIP archive contains an unsafe path.")
    target = (root / normalized).resolve()
    if not target.is_relative_to(root) or target == root:
        raise InvalidGeospatialFileError("ZIP archive contains an unsafe path.")
    return target


def _copy_limited(source: IO[bytes], sink: IO[bytes], limit: int) -> int:
    written = 0
    while True:
        chunk = source.read(_COPY_CHUNK_BYTES)
        if not chunk:
            break
        written += len(chunk)
        if written > limit:
            raise InvalidGeospatialFileError("ZIP archive exceeds the uncompressed size limit.")
        sink.write(chunk)
    return written
