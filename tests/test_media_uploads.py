"""TORY-53: shared image upload pipeline and its deployment wiring."""

import re
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image

from config import media


def image_bytes(fmt="PNG", size=(40, 30), mode="RGB", colour="red", **save_kwargs):
    buffer = BytesIO()
    Image.new(mode, size, colour).save(buffer, format=fmt, **save_kwargs)
    return buffer.getvalue()


def upload(data, name="picture.png", content_type="image/png"):
    return SimpleUploadedFile(name, data, content_type=content_type)


def decode(content):
    image = Image.open(BytesIO(content.read()))
    image.load()
    return image


class ProcessImageTests(SimpleTestCase):
    def test_accepts_jpeg_png_and_webp_and_reencodes_to_webp(self):
        for fmt in ("JPEG", "PNG", "WEBP"):
            with self.subTest(fmt=fmt):
                original = image_bytes(fmt)
                result = media.process_image(upload(original, f"x.{fmt.lower()}"))
                self.assertRegex(result.name, r"^[0-9a-f]{32}\.webp$")
                data = result.read()
                self.assertNotEqual(data, original)
                result.seek(0)
                self.assertEqual(decode(result).format, "WEBP")

    def test_each_upload_gets_a_fresh_random_name(self):
        data = image_bytes()
        names = {media.process_image(upload(data)).name for _ in range(3)}
        self.assertEqual(len(names), 3)

    def test_resizes_to_max_dimension_keeping_aspect_ratio(self):
        result = decode(media.process_image(upload(image_bytes(size=(2000, 1000)))))
        self.assertEqual(result.size, (512, 256))

    def test_small_images_are_not_enlarged(self):
        self.assertEqual(decode(media.process_image(upload(image_bytes(size=(64, 48))))).size, (64, 48))

    def test_strips_exif_including_gps(self):
        exif = Image.Exif()
        exif[0x010F] = "SpyCam"          # Make
        exif[0x8825] = {2: (1.0, 2.0, 3.0)}  # GPS IFD
        original = image_bytes("JPEG", exif=exif.tobytes())
        self.assertIn(b"SpyCam", original)
        result = media.process_image(upload(original, "photo.jpg", "image/jpeg"))
        data = result.read()
        self.assertNotIn(b"SpyCam", data)
        self.assertNotIn(b"Exif", data)
        self.assertFalse(Image.open(BytesIO(data)).getexif())

    def test_applies_exif_orientation_before_stripping(self):
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 90 degrees clockwise on display
        original = image_bytes("JPEG", size=(80, 40), exif=exif.tobytes())
        self.assertEqual(decode(media.process_image(upload(original, "p.jpg"))).size, (40, 80))

    def test_drops_bytes_appended_after_the_image(self):
        payload = b"<script>alert(document.cookie)</script>"
        result = media.process_image(upload(image_bytes() + payload))
        self.assertNotIn(payload, result.read())

    def test_keeps_transparency(self):
        result = decode(media.process_image(upload(image_bytes(mode="RGBA", colour=(0, 0, 0, 0)))))
        self.assertEqual(result.mode, "RGBA")

    def test_rejects_oversize_upload(self):
        big = upload(b"\0" * (media.MAX_UPLOAD_BYTES + 1))
        with self.assertRaises(ValidationError) as caught:
            media.process_image(big)
        self.assertEqual(caught.exception.code, "image_too_large")

    def test_rejects_renamed_non_images(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        cases = {
            "html as png": upload(b"<html><script>alert(1)</script></html>", "evil.png"),
            "svg as png": upload(svg, "evil.png"),
            "svg": upload(svg, "evil.svg", "image/svg+xml"),
            "empty": upload(b"", "empty.png"),
            "truncated png": upload(image_bytes()[:40], "cut.png"),
        }
        for label, bad in cases.items():
            with self.subTest(label), self.assertRaises(ValidationError) as caught:
                media.process_image(bad)
            self.assertEqual(caught.exception.code, "invalid_image")

    def test_rejects_other_real_image_formats(self):
        for fmt in ("GIF", "BMP", "TIFF"):
            with self.subTest(fmt=fmt), self.assertRaises(ValidationError):
                media.process_image(upload(image_bytes(fmt), f"x.{fmt.lower()}"))

    def test_rejects_decompression_bombs(self):
        # A tiny file that declares an enormous canvas.
        bomb = image_bytes("PNG", size=(8000, 8000), mode="1", colour=0)
        self.assertLess(len(bomb), media.MAX_UPLOAD_BYTES)
        with self.assertRaises(ValidationError) as caught:
            media.process_image(upload(bomb))
        self.assertEqual(caught.exception.code, "image_too_many_pixels")


class PictureForm(forms.Form):
    picture = media.ImageUploadField()


class ImageUploadFieldTests(SimpleTestCase):
    def test_field_is_optional_and_restricts_the_file_picker(self):
        form = PictureForm(data={}, files={})
        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data["picture"])
        self.assertIn('accept="image/jpeg,image/png,image/webp"', str(form["picture"]))

    def test_valid_upload_cleans_to_processed_file(self):
        form = PictureForm(data={}, files={"picture": upload(image_bytes())})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertTrue(form.cleaned_data["picture"].name.endswith(".webp"))

    def test_invalid_upload_is_a_form_error(self):
        form = PictureForm(data={}, files={"picture": upload(b"GIF89a not really", "x.png")})
        self.assertFalse(form.is_valid())
        self.assertIn("Upload a JPEG, PNG or WebP picture.", form.errors["picture"])


class StorageTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)

    def test_store_and_delete_after_commit(self):
        name = media.store_image(media.process_image(upload(image_bytes())), "avatars")
        self.assertRegex(name, r"^avatars/[0-9a-f]{32}\.webp$")
        self.assertTrue(default_storage.exists(name))
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            media.delete_image_after_commit(name)
        self.assertTrue(default_storage.exists(name), "deleted before commit")
        for callback in callbacks:
            callback()
        self.assertFalse(default_storage.exists(name))

    def test_delete_of_no_picture_is_a_no_op(self):
        with self.captureOnCommitCallbacks() as callbacks:
            media.delete_image_after_commit("")
        self.assertEqual(callbacks, [])


ROOT = Path(settings.BASE_DIR)


class MediaDeploymentConfigTests(SimpleTestCase):
    """Guards for the staging wiring; behaviour was checked against Caddy 2.11.9."""

    def test_settings(self):
        self.assertEqual(settings.MEDIA_URL, "/media/")
        self.assertEqual(settings.FILE_UPLOAD_PERMISSIONS, 0o644)

    def test_caddy_serves_only_webp_media_with_nosniff_and_sandbox(self):
        caddyfile = (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")
        block = caddyfile[caddyfile.index("handle @media"):caddyfile.index("\thandle {")]
        self.assertIn('X-Content-Type-Options "nosniff"', block)
        self.assertRegex(block, r"Content-Security-Policy \"default-src 'none'; sandbox")
        self.assertIn(r"\.webp$", block)
        self.assertIn("respond @not_picture 404", block)
        self.assertIn("img-src 'self' data:", caddyfile)

    def test_media_volume_is_shared_read_only_with_caddy(self):
        compose = (ROOT / "deploy" / "docker-compose.prod.yml").read_text(encoding="utf-8")
        self.assertIn("- media:/app/media", compose)
        self.assertIn("- media:/srv/media:ro", compose)
        self.assertRegex(compose, r"(?m)^volumes:\n(  \w+:\n)*  media:")

    def test_backups_and_restores_include_media(self):
        script = (ROOT / "deploy" / "deploy.sh").read_text(encoding="utf-8")
        self.assertIn("tar -C /app/media -czf -", script)
        restore_test = re.search(r"restore-test\)\n(.*?)\n        ;;", script, re.S).group(1)
        self.assertIn("media_archive_for", restore_test)
        restore = re.search(r"\n    restore\)\n(.*?)\n        ;;", script, re.S).group(1)
        self.assertIn("tar -C /app/media -xzf -", restore)

    def test_uploads_are_never_baked_into_the_image(self):
        self.assertIn("media", (ROOT / ".dockerignore").read_text(encoding="utf-8").split())
