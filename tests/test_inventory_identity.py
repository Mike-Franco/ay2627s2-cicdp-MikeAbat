"""TORY-54: inventory icon, colour and optional picture."""

import re
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from config.palette import TONE_KEYS
from inventory_access.icons import ICON_KEYS, ICONS
from inventory_access.models import (
    Business, BusinessMembership, Inventory, InventoryAssignment, InventoryChangeAuditEvent,
)
from receiving.management.commands.seed_demo import INVENTORIES, INVENTORY_LOOKS

ICON_DIR = Path(settings.BASE_DIR, "static", "tory", "icons")


def png(colour="red"):
    buffer = BytesIO()
    Image.new("RGB", (30, 30), colour).save(buffer, format="PNG")
    return SimpleUploadedFile("shelf.png", buffer.getvalue(), content_type="image/png")


class IconAssetTests(SimpleTestCase):
    def test_sprite_has_exactly_the_curated_icons_as_plain_shapes(self):
        sprite = (ICON_DIR / "lucide-sprite.svg").read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'<symbol id="([a-z-]+)"', sprite)), set(ICON_KEYS))
        self.assertEqual(len(ICONS), 24)
        for forbidden in ("<script", "on", "href", "<style", "<foreignObject"):
            self.assertNotRegex(sprite, rf"{forbidden}[a-z]*=" if forbidden == "on" else re.escape(forbidden))

    def test_isc_licence_is_shipped(self):
        licence = (ICON_DIR / "LICENSE-lucide.txt").read_text(encoding="utf-8")
        self.assertIn("ISC License", licence)
        self.assertIn("Lucide", licence)

    def test_demo_inventories_have_looks(self):
        self.assertEqual(INVENTORY_LOOKS["Pharmacy"], ("pill", "teal"))
        self.assertEqual(INVENTORY_LOOKS["Grocery"], ("shopping-cart", "orange"))
        self.assertLessEqual(set(INVENTORY_LOOKS), set(INVENTORIES))
        for icon, colour in INVENTORY_LOOKS.values():
            self.assertIn(icon, ICON_KEYS)
            self.assertIn(colour, TONE_KEYS)


class InventoryIdentityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Look business")
        cls.other_business = Business.objects.create(name="Other look business")
        cls.manager = users.create_user(email="look-manager@example.test")
        cls.staff = users.create_user(email="look-staff@example.test")
        cls.other_manager = users.create_user(email="look-other@example.test")
        manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        staff_role = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        other_role = BusinessMembership.objects.create(business=cls.other_business, user=cls.other_manager,
                                                       role="manager")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Cold room")
        cls.other_inventory = Inventory.objects.create(business=cls.other_business, name="Elsewhere")
        InventoryAssignment.objects.create(membership=manager_role, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=staff_role, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=other_role, inventory=cls.other_inventory)

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        override = override_settings(MEDIA_ROOT=self.media_root)
        override.enable()
        self.addCleanup(override.disable)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def edit(self, **data):
        payload = {"name": "Cold room", "icon": "snowflake", "colour": "sky", **data}
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("inventory-rename", args=[self.inventory.pk]), payload)

    def test_defaults_for_existing_and_name_only_inventories(self):
        self.assertEqual((self.inventory.icon, self.inventory.colour, self.inventory.picture.name),
                         ("package", "slate", ""))
        self.login(self.manager)
        self.client.post(reverse("inventory-create", args=[self.business.pk]), {"name": "Back room"})
        created = Inventory.objects.get(name="Back room")
        self.assertEqual((created.icon, created.colour), ("package", "slate"))

    def test_manager_creates_with_icon_colour_and_picture(self):
        self.login(self.manager)
        response = self.client.post(reverse("inventory-create", args=[self.business.pk]), {
            "name": "Pharmacy", "icon": "pill", "colour": "teal", "picture_upload": png(),
        })
        self.assertRedirects(response, reverse("inventory-list"), fetch_redirect_response=False)
        created = Inventory.objects.get(name="Pharmacy")
        self.assertEqual((created.icon, created.colour), ("pill", "teal"))
        self.assertRegex(created.picture.name, r"^inventories/[0-9a-f]{32}\.webp$")
        event = InventoryChangeAuditEvent.objects.get(inventory=created)
        self.assertEqual((event.action, event.after["icon"], event.after["colour"]), ("create", "pill", "teal"))

    def test_edit_is_audited_as_restyle_or_rename(self):
        self.login(self.manager)
        self.assertEqual(self.edit().status_code, 302)
        event = InventoryChangeAuditEvent.objects.get(inventory=self.inventory)
        self.assertEqual(event.action, "restyle")
        self.assertEqual((event.before["icon"], event.after["icon"]), ("package", "snowflake"))
        self.assertEqual((event.before["colour"], event.after["colour"]), ("slate", "sky"))
        self.edit(name="Chiller")
        self.assertEqual(InventoryChangeAuditEvent.objects.filter(inventory=self.inventory).latest("pk").action,
                         "rename")
        count = InventoryChangeAuditEvent.objects.count()
        self.edit(name="Chiller")
        self.assertEqual(InventoryChangeAuditEvent.objects.count(), count, "no-op edits are not audited")

    def test_invalid_icon_and_colour_rejected(self):
        self.login(self.manager)
        for data in ({"icon": "skull"}, {"colour": "chartreuse"}, {"icon": "<script>"}):
            with self.subTest(data=data):
                self.assertEqual(self.edit(**data).status_code, 400)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.icon, "package")
        for field, value in (("icon", "skull"), ("colour", "chartreuse")):
            with self.subTest(field=field), self.assertRaises(IntegrityError), transaction.atomic():
                Inventory.objects.filter(pk=self.inventory.pk).update(**{field: value})

    def test_picture_uses_shared_pipeline_and_replaced_files_are_deleted(self):
        self.login(self.manager)
        self.edit(picture_upload=png())
        self.inventory.refresh_from_db()
        first = self.inventory.picture.name
        self.assertTrue(default_storage.exists(first))
        bad = SimpleUploadedFile("x.png", b"<html><script>alert(1)</script></html>", content_type="image/png")
        response = self.edit(picture_upload=bad)
        self.assertContains(response, "Upload a JPEG, PNG or WebP picture.", status_code=400)
        self.edit(picture_upload=png("blue"))
        self.inventory.refresh_from_db()
        second = self.inventory.picture.name
        self.assertFalse(default_storage.exists(first))
        self.edit(remove_picture="on")
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.picture.name, "")
        self.assertFalse(default_storage.exists(second))

    def test_duplicate_name_discards_the_uploaded_picture(self):
        Inventory.objects.create(business=self.business, name="Taken")
        self.login(self.manager)
        response = self.edit(name="taken", picture_upload=png())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(Path(self.media_root).rglob("*.webp")), [])

    def test_staff_cannot_edit_and_other_business_is_404(self):
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse("inventory-rename", args=[self.inventory.pk])).status_code, 404)
        self.assertEqual(self.edit().status_code, 404)
        self.login(self.other_manager)
        self.assertEqual(self.edit().status_code, 404)
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.icon, "package")

    def test_badge_shows_icon_colour_or_picture(self):
        self.inventory.icon, self.inventory.colour = "snowflake", "sky"
        html = render_to_string("includes/inventory_badge.html", {"inventory": self.inventory})
        self.assertIn('class="inventory-mark tone-sky"', html)
        self.assertIn('lucide-sprite.svg#snowflake"', html)
        self.assertIn('<span class="inventory-badge-name">Cold room</span>', html)
        self.inventory.picture.name = "inventories/abc.webp"
        html = render_to_string("includes/inventory_badge.html", {"inventory": self.inventory, "icon_only": True})
        self.assertIn('src="/media/inventories/abc.webp"', html)
        self.assertNotIn("Cold room", html)

    def test_badge_appears_in_switcher_breadcrumb_and_inventory_list(self):
        Inventory.objects.filter(pk=self.inventory.pk).update(icon="snowflake", colour="sky")
        self.login(self.staff)
        page = self.client.get(reverse("inventory-products", args=[self.inventory.pk])).content.decode()
        switcher = page[page.index('class="inventory-switch"'):page.index("</summary>")]
        self.assertIn("lucide-sprite.svg#snowflake", switcher)
        crumb = re.search(r'<nav class="crumbs" aria-label="Breadcrumb">.*?</nav>', page, re.S).group(0)
        self.assertIn("tone-sky", crumb)
        self.assertContains(self.client.get(reverse("inventory-list")), "lucide-sprite.svg#snowflake")
