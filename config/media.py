"""Shared, safe image uploads (TORY-53).

Every uploaded picture (inventory pictures, profile photos) goes through
``process_image``: the bytes must decode as a JPEG, PNG or WebP image no larger
than ``MAX_UPLOAD_BYTES``; the pixels are then re-encoded to a fresh WebP file
no larger than ``MAX_DIMENSION`` on its longest side. Re-encoding keeps only
pixel data, so EXIF (including GPS location), comments, ICC profiles and
anything appended to or embedded in the original file are dropped. The stored
name is a random UUID, so it reveals nothing about the original file and cannot
be guessed.

Files are written with Django's default storage (``MEDIA_ROOT``). Staging serves
them straight from Caddy with ``nosniff`` and a sandboxing CSP; development
serves them through Django (``config/urls.py``).
"""

import uuid
from io import BytesIO

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 512
# Reject absurd canvases before decoding them (decompression bombs): a 2 MB
# PNG can otherwise expand to gigabytes of pixels.
MAX_SOURCE_PIXELS = 40_000_000
ALLOWED_FORMATS = frozenset({"JPEG", "PNG", "WEBP"})
ACCEPT_ATTRIBUTE = "image/jpeg,image/png,image/webp"
OUTPUT_EXTENSION = "webp"
WEBP_QUALITY = 85

INVALID_IMAGE_MESSAGE = "Upload a JPEG, PNG or WebP picture."
TOO_LARGE_MESSAGE = "Pictures must be 2 MB or smaller."


def _open_checked(data):
    """Open ``data`` (bytes) with Pillow, enforcing format and canvas limits."""
    image = Image.open(BytesIO(data))
    if image.format not in ALLOWED_FORMATS:
        image.close()
        raise ValidationError(INVALID_IMAGE_MESSAGE, code="invalid_image")
    width, height = image.size
    if width < 1 or height < 1 or width * height > MAX_SOURCE_PIXELS:
        image.close()
        raise ValidationError("That picture's dimensions are too large.", code="image_too_many_pixels")
    return image


def process_image(upload):
    """Validate ``upload`` and return a re-encoded WebP ``ContentFile``.

    Raises ``ValidationError`` for anything that is not a well-formed JPEG,
    PNG or WebP image within the size limits. The original bytes are never
    stored.
    """
    size = getattr(upload, "size", None)
    if size is None or size > MAX_UPLOAD_BYTES:
        raise ValidationError(TOO_LARGE_MESSAGE, code="image_too_large")
    if size == 0:
        raise ValidationError(INVALID_IMAGE_MESSAGE, code="invalid_image")
    upload.seek(0)
    data = upload.read()
    upload.seek(0)
    try:
        # verify() checks structure without decoding pixels; the image must be
        # reopened afterwards to be used.
        with _open_checked(data) as probe:
            probe.verify()
        with _open_checked(data) as image:
            image.seek(0)  # first frame only for animated WebP/PNG
            image = ImageOps.exif_transpose(image)
            has_alpha = image.mode in {"RGBA", "LA", "PA"} or (
                image.mode == "P" and "transparency" in image.info
            )
            image = image.convert("RGBA" if has_alpha else "RGB")
            image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
            output = BytesIO()
            # No exif/icc_profile arguments: the new file carries pixels only.
            image.save(output, format="WEBP", quality=WEBP_QUALITY, method=4)
    except ValidationError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError) as error:
        raise ValidationError(INVALID_IMAGE_MESSAGE, code="invalid_image") from error
    return ContentFile(output.getvalue(), name=f"{uuid.uuid4().hex}.{OUTPUT_EXTENSION}")


class ImageUploadField(forms.FileField):
    """Form field whose cleaned value is the processed ``ContentFile``."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("widget", forms.FileInput)
        kwargs.setdefault("help_text", "JPEG, PNG or WebP, up to 2 MB. Resized to 512 px; location data is removed.")
        super().__init__(**kwargs)
        self.widget.attrs.setdefault("accept", ACCEPT_ATTRIBUTE)

    def clean(self, data, initial=None):
        upload = super().clean(data, initial)
        if not upload or upload is initial:
            return None
        return process_image(upload)


def store_image(content, folder):
    """Save processed ``content`` under ``folder`` and return its storage name."""
    return default_storage.save(f"{folder}/{content.name}", content)


def delete_image_after_commit(name):
    """Delete a stored image once the surrounding transaction commits.

    Used when a picture is replaced or removed, so the old file goes only when
    the database no longer points at it.
    """
    if not name:
        return
    transaction.on_commit(lambda: default_storage.delete(name))
