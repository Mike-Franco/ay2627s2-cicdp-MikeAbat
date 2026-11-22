from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.sessions import ACTIVE_KEY, CREATED_KEY

OLD = "original-account-passphrase"
NEW = "brand-new-account-passphrase"


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AccountPasswordTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(email="account@example.test", password=OLD)
        self.url = reverse("account")

    def signed_in_client(self):
        client = Client()
        client.force_login(self.user)
        session = client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()
        return client

    def change(self, client, old=OLD, new=NEW, confirm=None):
        return client.post(self.url, {"old_password": old, "new_password1": new,
                                      "new_password2": new if confirm is None else confirm})

    def test_requires_sign_in(self):
        self.assertRedirects(self.client.get(self.url), reverse("login"), fetch_redirect_response=False)

    def test_page_and_sidebar_link(self):
        client = self.signed_in_client()
        response = client.get(self.url)
        self.assertContains(response, ">Current password</label>")
        self.assertContains(response, "Use at least 15 characters.")
        self.assertContains(response, f'class="account-link" href="{self.url}"')

    def test_rejects_wrong_current_password(self):
        response = self.change(self.signed_in_client(), old="not-the-current-passphrase")
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_applies_password_validators_with_friendly_messages(self):
        client = self.signed_in_client()
        for new, message in (("short", "Use at least 15 characters."),
                             ("account@example.test1", "Choose a password less similar to your account details.")):
            with self.subTest(new=new):
                response = self.change(client, new=new)
                self.assertContains(response, message, status_code=400)
        self.assertContains(self.change(client, confirm="something-else-entirely"), "match", status_code=400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))

    def test_success_keeps_this_session_and_signs_out_others(self):
        current, other = self.signed_in_client(), self.signed_in_client()
        bystander = get_user_model().objects.create_user(email="bystander@example.test", password=OLD)
        bystander_client = Client()
        bystander_client.force_login(bystander)
        response = self.change(current)
        self.assertRedirects(response, self.url, fetch_redirect_response=False)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW))
        page = current.get(self.url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Password changed. Signed out 1 other session.")
        self.assertRedirects(other.get(self.url), reverse("login"), fetch_redirect_response=False)
        user_sessions = [s for s in Session.objects.all() if s.get_decoded().get("_auth_user_id") == str(self.user.pk)]
        self.assertEqual(len(user_sessions), 1)
        self.assertTrue(Session.objects.filter(session_key=bystander_client.session.session_key).exists())

    def test_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        session = client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()
        self.assertEqual(self.change(client).status_code, 403)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(OLD))
