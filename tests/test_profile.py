"""TORY-55: own profile page, avatars and display names."""

import shutil
import tempfile
from io import BytesIO
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment
from receiving.services import receive_manual


def png(colour="red"):
    buffer = BytesIO()
    Image.new("RGB", (40, 40), colour).save(buffer, format="PNG")
    return SimpleUploadedFile("me.png", buffer.getvalue(), content_type="image/png")


class ProfileTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.business = Business.objects.create(name="Profile business")
        cls.manager = users.create_user(email="profile-manager@example.test")
        cls.staff = users.create_user(email="profile-staff@example.test", first_name="Sam", last_name="Tan")
        manager_role = BusinessMembership.objects.create(business=cls.business, user=cls.manager, role="manager")
        staff_role = BusinessMembership.objects.create(business=cls.business, user=cls.staff, role="staff")
        cls.inventory = Inventory.objects.create(business=cls.business, name="Dispensary")
        InventoryAssignment.objects.create(membership=manager_role, inventory=cls.inventory)
        InventoryAssignment.objects.create(membership=staff_role, inventory=cls.inventory)

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

    def save_profile(self, **changes):
        data = {"display_name": "", "job_title": "", "phone": "", "avatar_colour": "slate", **changes}
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse("account-profile"), data)


class ProfilePageTests(ProfileTestCase):
    def test_requires_sign_in(self):
        self.assertRedirects(self.client.get(reverse("account")), reverse("login"), fetch_redirect_response=False)
        response = self.client.post(reverse("account-profile"), {"display_name": "x"})
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)

    def test_staff_and_manager_see_read_only_facts(self):
        for user, role in ((self.staff, "Staff"), (self.manager, "Manager")):
            with self.subTest(role=role):
                self.login(user)
                response = self.client.get(reverse("account"))
                self.assertContains(response, user.email)
                self.assertContains(response, f"{role} at Profile business")
                self.assertContains(response, "Dispensary")
                self.assertContains(response, "Account created")
                self.assertContains(response, "Last sign-in")
                self.assertContains(response, 'name="display_name"')
                self.assertContains(response, ">Current password</label>")
                self.assertNotContains(response, 'name="email"')

    def test_sidebar_user_area_links_to_profile(self):
        self.login(self.staff)
        response = self.client.get(reverse("inventory-list"))
        self.assertContains(response, f'<a class="account-link" href="{reverse("account")}"')
        self.assertContains(response, "<strong>Sam Tan</strong>")

    def test_deactivated_users_cannot_view_or_save(self):
        self.login(self.staff)
        get_user_model().objects.filter(pk=self.staff.pk).update(is_active=False)
        self.assertRedirects(self.client.get(reverse("account")), reverse("login"), fetch_redirect_response=False)
        self.login(self.staff)
        response = self.save_profile(display_name="Ghost")
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.display_name, "")

    def test_profile_save_is_post_only(self):
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse("account-profile")).status_code, 405)


class ProfileEditTests(ProfileTestCase):
    def test_saves_own_profile_with_whitespace_tidied(self):
        self.login(self.staff)
        response = self.save_profile(display_name="  Sammy   T  ", job_title=" Pharmacy  assistant ",
                                     phone=" +65 6123-4567 ", avatar_colour="teal")
        self.assertRedirects(response, reverse("account"), fetch_redirect_response=False)
        self.staff.refresh_from_db()
        self.assertEqual((self.staff.display_name, self.staff.job_title, self.staff.phone, self.staff.avatar_colour),
                         ("Sammy T", "Pharmacy assistant", "+65 6123-4567", "teal"))
        self.assertContains(self.client.get(reverse("account")), "Profile saved.")

    def test_cannot_change_email_or_another_users_profile(self):
        self.login(self.staff)
        self.save_profile(display_name="Me", email="hijack@example.test", pk=self.manager.pk, id=self.manager.pk)
        self.staff.refresh_from_db()
        self.manager.refresh_from_db()
        self.assertEqual(self.staff.email, "profile-staff@example.test")
        self.assertEqual(self.staff.display_name, "Me")
        self.assertEqual(self.manager.display_name, "")

    def test_validation(self):
        self.login(self.staff)
        cases = {
            "display name too long": {"display_name": "x" * 61},
            "job title too long": {"job_title": "x" * 61},
            "letters in phone": {"phone": "call me maybe"},
            "phone too short": {"phone": "123"},
            "phone too long": {"phone": "1" * 30},
            "colour not in palette": {"avatar_colour": "chartreuse"},
        }
        for label, data in cases.items():
            with self.subTest(label):
                response = self.save_profile(**data)
                self.assertEqual(response.status_code, 400)
        for phone in ("+65 6123 4567", "61234567", "(02) 9374-4000", "+1 (555) 010-9999"):
            with self.subTest(phone=phone):
                self.assertEqual(self.save_profile(phone=phone).status_code, 302)

    def test_invalid_submission_does_not_leak_into_the_page(self):
        self.login(self.staff)
        response = self.save_profile(display_name="x" * 61)
        self.assertContains(response, "<strong>Sam Tan</strong>", status_code=400)

    def test_database_rejects_colours_outside_the_palette(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            get_user_model().objects.filter(pk=self.staff.pk).update(avatar_colour="chartreuse")


class ProfilePhotoTests(ProfileTestCase):
    def test_upload_replace_and_remove(self):
        self.login(self.staff)
        self.assertEqual(self.save_profile(photo_upload=png()).status_code, 302)
        self.staff.refresh_from_db()
        first = self.staff.photo.name
        self.assertRegex(first, r"^avatars/[0-9a-f]{32}\.webp$")
        self.assertTrue(default_storage.exists(first))
        self.assertContains(self.client.get(reverse("account")), f'src="/media/{first}"')

        self.save_profile(photo_upload=png("blue"))
        self.staff.refresh_from_db()
        second = self.staff.photo.name
        self.assertNotEqual(first, second)
        self.assertFalse(default_storage.exists(first), "replaced photo should be deleted")
        self.assertTrue(default_storage.exists(second))

        self.save_profile(remove_photo="on")
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.photo.name, "")
        self.assertFalse(default_storage.exists(second))

    def test_rejects_non_images_and_keeps_the_old_photo(self):
        self.login(self.staff)
        self.save_profile(photo_upload=png())
        self.staff.refresh_from_db()
        kept = self.staff.photo.name
        fake = SimpleUploadedFile("me.png", b"<svg onload=alert(1)>", content_type="image/png")
        response = self.save_profile(photo_upload=fake)
        self.assertContains(response, "Upload a JPEG, PNG or WebP picture.", status_code=400)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.photo.name, kept)
        self.assertTrue(default_storage.exists(kept))

    def test_new_photo_and_remove_together_is_an_error(self):
        self.login(self.staff)
        self.save_profile(photo_upload=png())
        response = self.save_profile(photo_upload=png("blue"), remove_photo="on")
        self.assertEqual(response.status_code, 400)


class AvatarTests(ProfileTestCase):
    def render(self, user, **extra):
        return render_to_string("includes/user_avatar.html", {"user": user, **extra})

    def test_initials_and_display_label_fallbacks(self):
        user = get_user_model()(email="zoe@example.test")
        self.assertEqual((user.initials, user.display_label), ("Z", "zoe@example.test"))
        user.first_name, user.last_name = "Ada", "Lovelace"
        self.assertEqual((user.initials, user.display_label), ("AL", "Ada Lovelace"))
        user.display_name = "Mary Ann  de Souza"
        self.assertEqual((user.initials, user.display_label), ("MS", "Mary Ann  de Souza"))
        user.display_name = "  "
        self.assertEqual(user.display_label, "Ada Lovelace")

    def test_initials_circle_uses_chosen_colour(self):
        self.staff.avatar_colour = "rose"
        html = self.render(self.staff, size="sm")
        self.assertIn('class="avatar avatar-sm tone-rose" aria-hidden="true">ST<', html)
        self.assertNotIn("<img", html)

    def test_photo_replaces_initials(self):
        self.staff.photo.name = "avatars/abc.webp"
        html = self.render(self.staff, with_name=True)
        self.assertIn('<img class="avatar avatar-md avatar-photo" src="/media/avatars/abc.webp" alt=""', html)
        self.assertIn('<span class="user-ref-name">Sam Tan</span>', html)

    def test_history_and_receipt_show_display_names_not_emails(self):
        get_user_model().objects.filter(pk=self.manager.pk).update(display_name="Head Pharmacist")
        product = Product.objects.create(business=self.business, sku="PR-1", name="Plasters",
                                         base_unit_label="box", expiry_tracking_required=False)
        InventoryProduct.objects.create(inventory=self.inventory, product=product)
        batch, _created = receive_manual(user_id=self.manager.pk, inventory_id=self.inventory.pk, product_id=product.pk,
                               request_token=uuid4(), quantity_units=3, expiry_date=None)
        self.login(self.staff)
        history = self.client.get(reverse("stock-history", args=[self.inventory.pk, product.pk]))
        self.assertContains(history, '<span class="user-ref-name">Head Pharmacist</span>')
        self.assertNotContains(history, "profile-manager@example.test")
        self.login(self.manager)
        receipt = self.client.get(reverse("receipt-confirmation", args=[batch.pk]))
        self.assertContains(receipt, '<span class="user-ref-name">Head Pharmacist</span>')


class StaffListProfileTests(ProfileTestCase):
    def test_manager_sees_display_name_job_title_and_phone(self):
        get_user_model().objects.filter(pk=self.staff.pk).update(
            display_name="Sammy", job_title="Dispenser", phone="+65 6123 4567", avatar_colour="green")
        self.login(self.manager)
        url = reverse("manager-staff", args=[self.business.pk])
        response = self.client.get(url)
        self.assertContains(response, '<span class="user-ref-name">Sammy</span>')
        self.assertContains(response, 'tone-green')
        self.assertContains(response, "Dispenser")
        self.assertContains(response, '<a href="tel:+6561234567">+65 6123 4567</a>')
        self.assertEqual(self.client.get(url, {"q": "Sammy"}).context["page"].paginator.count, 1)
        self.assertEqual(self.client.get(url, {"q": "dispens"}).context["page"].paginator.count, 1)
        self.assertEqual(self.client.get(url, {"sort": "-name"}).status_code, 200)

    def test_staff_cannot_open_the_staff_list(self):
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse("manager-staff", args=[self.business.pk])).status_code, 404)
