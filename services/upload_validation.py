"""Bounded, streaming primitives for untrusted file uploads."""

from __future__ import annotations

import os
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


UPLOAD_CHUNK_BYTES = 64 * 1024
UPLOAD_HEADER_BYTES = 4 * 1024
MAX_UPLOAD_FILENAME_CHARS = 255
GENERIC_MIME_TYPES = {'', 'application/octet-stream'}


class UploadValidationError(ValueError):
    """Raised when an uploaded value does not meet the public contract."""


class UploadStorageError(RuntimeError):
    """Raised when a temporary upload cannot be safely written or moved."""


class ChunkValidator(Protocol):
    """Optional incremental validator used while a stream is copied."""

    def consume(self, chunk: bytes) -> None:
        """Validate one chunk before it reaches persistent storage."""

    def finish(self) -> None:
        """Validate any state left after the final chunk."""


@dataclass(frozen=True)
class StagedUpload:
    """A fully written temporary file plus the bounded metadata needed by callers."""

    path: Path
    size_bytes: int
    header: bytes
    captured_bytes: bytes


def normalize_upload_filename(value: object) -> tuple[str, str]:
    """Return a display-safe basename and lower-case extension for an upload."""
    raw_name = str(value or '')
    if '\x00' in raw_name:
        raise UploadValidationError('文件名无效')

    # Normalize before stripping path components so full-width separators cannot bypass it.
    normalized = unicodedata.normalize('NFKC', raw_name).replace('\\', '/')
    filename = normalized.rsplit('/', 1)[-1].strip()
    if not filename or filename in {'.', '..'}:
        raise UploadValidationError('文件名为空')
    if len(filename) > MAX_UPLOAD_FILENAME_CHARS:
        raise UploadValidationError(f'文件名不能超过 {MAX_UPLOAD_FILENAME_CHARS} 个字符')
    if any(ord(character) < 32 or ord(character) == 127 for character in filename):
        raise UploadValidationError('文件名包含非法字符')
    if '.' not in filename:
        raise UploadValidationError('文件缺少扩展名')

    extension = filename.rsplit('.', 1)[-1].lower()
    if not extension:
        raise UploadValidationError('文件缺少扩展名')
    return filename, extension


def normalize_mime_type(value: object) -> str:
    """Normalize a client-provided Content-Type without treating it as authoritative."""
    return str(value or '').split(';', 1)[0].strip().lower()


def validate_reported_mime(reported_mime: object, allowed_mime_types: set[str], message: str) -> None:
    """Reject an explicit client MIME type that conflicts with an allowed format."""
    normalized = normalize_mime_type(reported_mime)
    if normalized not in GENERIC_MIME_TYPES and normalized not in allowed_mime_types:
        raise UploadValidationError(message)


def sniff_image_mime_type(header: bytes) -> str | None:
    """Identify the supported raster image formats from their immutable signatures."""
    if header.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if header.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if header.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return 'image/webp'
    return None


def stage_upload(
    stream,
    directory: Path,
    max_bytes: int,
    *,
    capture_bytes: int = 0,
    validator: ChunkValidator | None = None,
) -> StagedUpload:
    """Copy a stream once into a temporary file, enforcing a hard byte ceiling.

    The temporary file is removed on every failure.  Callers must move it into
    its final generated path or call :func:`cleanup_upload_file` afterwards.
    """
    if max_bytes < 1:
        raise UploadStorageError('上传大小限制无效')

    temporary_path: Path | None = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix='.upload-',
            suffix='.part',
            dir=directory,
        )
        temporary_path = Path(temporary_name)
        total_bytes = 0
        header = bytearray()
        captured = bytearray()

        with os.fdopen(descriptor, 'wb') as destination:
            while True:
                chunk = stream.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                if not isinstance(chunk, bytes):
                    raise UploadStorageError('上传文件读取失败')

                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise UploadValidationError('文件超过允许的大小限制')
                if validator is not None:
                    validator.consume(chunk)
                if len(header) < UPLOAD_HEADER_BYTES:
                    header.extend(chunk[:UPLOAD_HEADER_BYTES - len(header)])
                if len(captured) < capture_bytes:
                    captured.extend(chunk[:capture_bytes - len(captured)])
                destination.write(chunk)

            if validator is not None:
                validator.finish()
        if total_bytes == 0:
            raise UploadValidationError('文件不能为空')
        return StagedUpload(
            path=temporary_path,
            size_bytes=total_bytes,
            header=bytes(header),
            captured_bytes=bytes(captured),
        )
    except UploadValidationError:
        if temporary_path is not None:
            cleanup_upload_file(temporary_path)
        raise
    except UploadStorageError:
        if temporary_path is not None:
            cleanup_upload_file(temporary_path)
        raise
    except Exception as exc:
        if temporary_path is not None:
            cleanup_upload_file(temporary_path)
        raise UploadStorageError('上传文件读取失败') from exc


def cleanup_upload_file(path: Path | None) -> None:
    """Best-effort deletion for a staged or rolled-back file path."""
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # The original upload error is more useful than a cleanup failure.
        pass
