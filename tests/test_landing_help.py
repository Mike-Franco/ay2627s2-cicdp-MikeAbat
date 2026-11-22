"""TORY-60: public landing page and signed-in Help page."""

import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.public_views import HELP_SECTIONS
from accounts.sessions import ACTIVE_KEY, CREATED_KEY
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment


def anchors_resolve(html):
    ids = set(re.findall(r'\sid="([^"]+)"', html))
    links = set(re.findall(r'href="#([^"]+)"', html))
    return links - ids


class LandingHelpTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        business = Business.objects.create(name="Help business")
        cls.manager = users.create_user(email="help-manager@example.test")
        cls.staff = users.create_user(email="help-staff@example.test")
        inventory = Inventory.objects.create(business=business, name="Help shelf")
        for user, role in ((cls.manager, "manager"), (cls.staff, "staff")):
            membership = BusinessMembership.objects.create(business=business, user=user, role=role)
            InventoryAssignment.objects.create(membership=membership, inventory=inventory)

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session[CREATED_KEY] = session[ACTIVE_KEY] = timezone.now().timestamp()
        session.save()

    def test_landing_renders_signed_out(self):
        response = self.client.get(reverse("landing"))
        self.assertEqual(reverse("landing"), "/")
        self.assertContains(response, "Inventory made simple: track stock, catch expiries, know what to reorder.")
        self.assertContains(response, f'href="{reverse("login")}"')
        self.assertContains(response, "CA1 student project")
        self.assertContains(response, 'href="https://github.com/Mike-Franco/ay2627s2-cicdp-MikeAbat"')
        self.assertNotContains(response, 'id="workspace-sidebar"')
        html = response.content.decode()
        self.assertEqual(anchors_resolve(html), set())
        external_scripts = [src for src in re.findall(r'<script[^>]+src="([^"]+)"', html) if "://" in src]
        self.assertEqual(external_scripts, [], "no third-party or tracking scripts on the landing page")

    def test_signed_in_users_go_straight_to_the_dashboard(self):
        for user in (self.manager, self.staff):
            self.login(user)
            self.assertRedirects(self.client.get("/"), reverse("home"))
        self.assertEqual(reverse("home"), "/dashboard/")

    def test_dashboard_still_requires_sign_in(self):
        self.assertRedirects(self.client.get(reverse("home")), reverse("login"), fetch_redirect_response=False)

    def test_help_requires_sign_in(self):
        self.assertRedirects(self.client.get(reverse("help")), reverse("login"), fetch_redirect_response=False)

    def test_help_has_every_section_and_no_broken_anchors(self):
        for user in (self.manager, self.staff):
            self.login(user)
            response = self.client.get(reverse("help"))
            self.assertEqual(response.status_code, 200)
            html = response.content.decode()
            self.assertEqual(anchors_resolve(html), set())
            for anchor, title in HELP_SECTIONS:
                with self.subTest(anchor=anchor):
                    self.assertIn(f'id="{anchor}"', html)
                    self.assertIn(f'<a href="#{anchor}">{title}</a>', html)
            self.assertIn('class="role-badge role-manager"', html)
            self.assertIn("3 × 4 + 5 = 17", html)

    def test_sidebar_links_to_help_for_every_role(self):
        for user in (self.manager, self.staff):
            self.login(user)
            self.assertContains(self.client.get(reverse("home")), f'href="{reverse("help")}"')
