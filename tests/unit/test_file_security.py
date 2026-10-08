"""Upload path and ZIP safety."""

import stat
import zipfile
from pathlib import Path

import pytest

from app.core.exceptions import InvalidGeospatialFileError, UnsupportedFileFormatError
from app.utils.file_utils import safe_extract_zip, sanitize_filename


def test_filename_discards_directory_parts() -> None:
    assert sanitize_filename("../../etc/passwd.kml") == "passwd.kml"
    assert sanitize_filename("folder\\survey.ZIP") == "survey.zip"


def test_filename_rejects_a_blank_name() -> None:
    with pytest.raises(UnsupportedFileFormatError):
        sanitize_filename("   ")


def test_zip_slip_does_not_escape_the_destination(tmp_path: Path) -> None:
    archive_path = tmp_path / "slip.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", b"pwned")
        archive.writestr("nested/../../outside.txt", b"pwned")

    with pytest.raises(InvalidGeospatialFileError, match="unsafe path"):
        safe_extract_zip(
            archive_path,
            tmp_path / "extract",
            max_entries=10,
            max_uncompressed_bytes=10_000,
        )

    assert not (tmp_path / "outside.txt").exists()


def test_absolute_zip_member_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "absolute.zip"
    escaped = tmp_path / "escaped.txt"
    with zipfile.ZipFile(archive_path, "w") as archive:
        info = zipfile.ZipInfo(str(escaped))
        archive.writestr(info, b"pwned")

    member_name = zipfile.ZipFile(archive_path).namelist()[0]
    if not member_name.startswith("/"):
        pytest.skip("This Python normalizes absolute ZIP names before they can be tested.")

    with pytest.raises(InvalidGeospatialFileError, match="absolute path"):
        safe_extract_zip(
            archive_path,
            tmp_path / "extract",
            max_entries=10,
            max_uncompressed_bytes=10_000,
        )
    assert not escaped.exists()


def test_zip_symlink_entry_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "link.zip"
    info = zipfile.ZipInfo("link.shp")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(info, b"/tmp/not-a-real-target")

    with pytest.raises(InvalidGeospatialFileError, match="symlink"):
        safe_extract_zip(
            archive_path,
            tmp_path / "extract",
            max_entries=10,
            max_uncompressed_bytes=10_000,
        )


def test_zip_entry_count_and_uncompressed_size_are_capped(tmp_path: Path) -> None:
    many = tmp_path / "many.zip"
    with zipfile.ZipFile(many, "w") as archive:
        archive.writestr("a.txt", b"a")
        archive.writestr("b.txt", b"b")

    with pytest.raises(InvalidGeospatialFileError, match="exceeds the limit"):
        safe_extract_zip(many, tmp_path / "out-a", max_entries=1, max_uncompressed_bytes=10_000)

    large = tmp_path / "large.zip"
    with zipfile.ZipFile(large, "w") as archive:
        archive.writestr("layer.shp", b"x" * 5_000)

    with pytest.raises(InvalidGeospatialFileError, match="uncompressed"):
        safe_extract_zip(large, tmp_path / "out-b", max_entries=10, max_uncompressed_bytes=1_000)
