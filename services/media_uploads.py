"""Media upload validation and storage helpers."""

from __future__ import annotations

import uuid
from pathlib import Path

import config
from services.upload_validation import (
    UploadStorageError,
    UploadValidationError,
    cleanup_upload_file,
    normalize_upload_filename,
    sniff_image_mime_type,
    stage_upload,
    validate_reported_mime,
)


ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
IMAGE_MIME_TYPES = {
    'png': 'image/png',
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'gif': 'image/gif',
    'webp': 'image/webp',
}
MAX_ADMIN_IMAGE_BYTES = 10 * 1024 * 1024


class MediaUploadError(ValueError):
    pass


def admin_image_request_limit_bytes() -> int:
    """Leave enough room for multipart headers while bounding an image request."""
    return MAX_ADMIN_IMAGE_BYTES + 64 * 1024


def _validate_image_upload(extension: str, reported_mime: object, header: bytes) -> None:
    """Require the filename, reported MIME and immutable file signature to agree."""
    expected_mime = IMAGE_MIME_TYPES[extension]
    allowed_reported_mimes = {expected_mime}
    if expected_mime == 'image/jpeg':
        allowed_reported_mimes.add('image/jpg')
    validate_reported_mime(
        reported_mime,
        allowed_reported_mimes,
        '上传文件不是受支持的图片类型',
    )
    detected_mime = sniff_image_mime_type(header)
    if detected_mime != expected_mime:
        raise UploadValidationError('图片内容与文件扩展名不匹配')


def save_admin_image(file_storage) -> str:
    """Validate and store an admin-uploaded image.

    Returns the static filename path, for example ``images/<name>.png``.
    """
    if not file_storage:
        raise MediaUploadError('没有文件')
    staged_upload = None
    try:
        _, extension = normalize_upload_filename(file_storage.filename)
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise UploadValidationError('不支持的图片格式')

        upload_directory = Path(config.UPLOAD_DIR)
        staged_upload = stage_upload(
            file_storage.stream,
            upload_directory,
            MAX_ADMIN_IMAGE_BYTES,
        )
        _validate_image_upload(extension, file_storage.mimetype, staged_upload.header)

        filename = f"{uuid.uuid4().hex}.{extension}"
        try:
            staged_upload.path.replace(upload_directory / filename)
        except OSError as exc:
            raise UploadStorageError('图片保存失败') from exc
        staged_upload = None
        return f'images/{filename}'
    except UploadValidationError as exc:
        raise MediaUploadError(str(exc)) from exc
    except UploadStorageError as exc:
        raise MediaUploadError(str(exc)) from exc
    finally:
        if staged_upload is not None:
            cleanup_upload_file(staged_upload.path)
