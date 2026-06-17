"""Media upload validation and storage helpers."""

from __future__ import annotations

import uuid
from pathlib import Path

import config


ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}


class MediaUploadError(ValueError):
    pass


def save_admin_image(file_storage) -> str:
    """Validate and store an admin-uploaded image.

    Returns the static filename path, for example ``images/<name>.png``.
    """
    if not file_storage:
        raise MediaUploadError('没有文件')
    original_name = str(file_storage.filename or '').strip()
    if not original_name:
        raise MediaUploadError('文件名为空')
    if '.' not in original_name:
        raise MediaUploadError('不支持的图片格式')
    ext = original_name.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise MediaUploadError('不支持的图片格式')
    Path(config.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(Path(config.UPLOAD_DIR) / filename)
    return f'images/{filename}'
