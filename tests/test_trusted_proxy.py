from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, TestCase, modify_settings, override_settings
from django.urls import reverse

from accounts import throttle
from accounts.models import LoginFailure
from config.proxy import TrustedProxyMiddleware


def remote_addr(**meta):
    seen = {}

    def view(request):
        seen["addr"] = request.META["REMOTE_ADDR"]
        return HttpResponse()

    TrustedProxyMiddleware(view)(RequestFactory().get("/", REMOTE_ADDR="172.18.0.5", **meta))
    return seen["addr"]


class TrustedProxyMiddlewareTests(SimpleTestCase):
    def test_uses_address_appended_by_proxy(self):
        self.assertEqual(remote_addr(HTTP_X_FORWARDED_FOR="203.0.113.7"), "203.0.113.7")

    def test_ignores_client_supplied_entries_before_the_proxy_entry(self):
        self.assertEqual(remote_addr(HTTP_X_FORWARDED_FOR="10.9.9.9, 198.51.100.4"), "198.51.100.4")

    def test_accepts_ipv6(self):
        self.assertEqual(remote_addr(HTTP_X_FORWARDED_FOR="2001:db8::1"), "2001:db8::1")

    def test_keeps_socket_address_without_a_valid_header(self):
        for value in ("", " ", "not-an-ip", "203.0.113.7, "):
            with self.subTest(value=value):
                self.assertEqual(remote_addr(HTTP_X_FORWARDED_FOR=value), "172.18.0.5")
        self.assertEqual(remote_addr(), "172.18.0.5")


@override_settings(
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    SECURE_SSL_REDIRECT=True,
)
@modify_settings(MIDDLEWARE={"prepend": "config.proxy.TrustedProxyMiddleware"})
class TrustedProxyLoginTests(TestCase):
    def post_login(self, client_ip):
        return self.client.post(
            reverse("login"), {"email": "someone@example.test", "password": "wrong"},
            REMOTE_ADDR="172.18.0.5", HTTP_X_FORWARDED_FOR=client_ip, HTTP_X_FORWARDED_PROTO="https",
        )

    def test_throttle_buckets_by_forwarded_client_not_proxy(self):
        self.assertEqual(self.post_login("203.0.113.7").status_code, 200)
        failure = LoginFailure.objects.get()
        self.assertEqual(failure.ip_key, throttle._key("ip", "203.0.113.7"))
        self.assertNotEqual(failure.ip_key, throttle._key("ip", "172.18.0.5"))

    def test_proxy_scheme_header_satisfies_https_redirect(self):
        self.assertEqual(self.client.get(reverse("login"), HTTP_X_FORWARDED_PROTO="https").status_code, 200)
        self.assertEqual(self.client.get(reverse("login")).status_code, 301)
