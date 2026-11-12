from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth.models import User
from django.core.exceptions import SuspiciousOperation
from django.test import TestCase, override_settings
from django.urls import reverse
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from pinot_noir.authentication import GoogleOIDCAuthenticationBackend

CLIENT_ID = "google-client"
CLIENT_SECRET = "google-secret"
FAILURE_URL = "/login/?oauth=failed"


@override_settings(OIDC_RP_CLIENT_ID=CLIENT_ID, OIDC_RP_CLIENT_SECRET=CLIENT_SECRET)
class GoogleOAuthTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", email="Alice@example.com")
        self.google_url = reverse("oidc_authentication_init")
        self.callback_url = reverse("oidc_authentication_callback")
        self.page_url = reverse("merges_schedule:index")

    def callback(self, claims, next_url=None):
        params = {"next": next_url} if next_url else {}
        response = self.client.get(self.google_url, params)
        state = parse_qs(urlparse(response["Location"]).query)["state"][0]
        with (
            patch.object(
                GoogleOIDCAuthenticationBackend,
                "get_token",
                return_value={"id_token": "id-token", "access_token": "access-token"},
            ),
            patch.object(
                GoogleOIDCAuthenticationBackend,
                "verify_token",
                return_value={"sub": "google-user"},
            ),
            patch.object(
                GoogleOIDCAuthenticationBackend,
                "get_userinfo",
                return_value=claims,
            ),
        ):
            return self.client.get(
                self.callback_url, {"state": state, "code": "authorization-code"}
            )

    def assert_login_rejected(self, response):
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], FAILURE_URL)
        self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.get(FAILURE_URL)
        self.assertContains(
            response,
            "Google sign-in was not completed or did not match an active Pinot Noir account",
        )

    def test_login_link_requires_configuration(self):
        with self.settings(OIDC_RP_CLIENT_ID="", OIDC_RP_CLIENT_SECRET=""):
            response = self.client.get(reverse("login"))
            self.assertNotContains(response, "Continue with Google")

        response = self.client.get(reverse("login"), {"next": self.page_url})
        google_href = f"{self.google_url}?next={self.page_url}"
        self.assertContains(response, f'href="{google_href}"')
        self.assertContains(response, "Continue with Google")

    def test_authorization_redirect_uses_google_oidc(self):
        response = self.client.get(self.google_url, {"next": self.page_url})
        location = urlparse(response["Location"])
        self.assertEqual(
            (location.scheme, location.netloc, location.path),
            ("https", "accounts.google.com", "/o/oauth2/v2/auth"),
        )
        params = parse_qs(location.query)
        self.assertEqual(params["response_type"], ["code"])
        self.assertEqual(params["scope"], ["openid email"])
        self.assertEqual(params["client_id"], [CLIENT_ID])
        self.assertEqual(params["redirect_uri"], [f"http://testserver{self.callback_url}"])
        self.assertTrue(params["state"][0])
        self.assertTrue(params["nonce"][0])
        self.assertEqual(self.client.session["oidc_login_next"], self.page_url)

    def test_verified_email_logs_in_matching_user_case_insensitively(self):
        response = self.callback(
            {"email": "alice@EXAMPLE.COM", "email_verified": True},
            next_url=self.page_url,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.page_url)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)
        self.assertEqual(User.objects.count(), 1)

    def test_unknown_email_is_rejected_without_creating_user(self):
        response = self.callback({"email": "unknown@example.com", "email_verified": True})
        self.assert_login_rejected(response)
        self.assertEqual(User.objects.count(), 1)

    def test_unverified_email_is_rejected(self):
        response = self.callback({"email": self.user.email, "email_verified": False})
        self.assert_login_rejected(response)

    def test_inactive_user_is_rejected(self):
        self.user.is_active = False
        self.user.save()
        response = self.callback({"email": self.user.email, "email_verified": True})
        self.assert_login_rejected(response)

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user("bob", email=self.user.email.upper())
        response = self.callback({"email": self.user.email, "email_verified": True})
        self.assert_login_rejected(response)

    def test_unsafe_next_url_is_not_used(self):
        response = self.callback(
            {"email": self.user.email, "email_verified": True},
            next_url="https://evil.example/phishing",
        )
        self.assertEqual(response["Location"], reverse("root-redirect"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_id_token_must_have_google_audience_and_issuer(self):
        backend = GoogleOIDCAuthenticationBackend()
        valid = {"aud": CLIENT_ID, "iss": "https://accounts.google.com"}
        with patch.object(OIDCAuthenticationBackend, "verify_token", return_value=valid):
            self.assertEqual(backend.verify_token("id-token"), valid)

        invalid_payloads = (
            {**valid, "aud": "another-client"},
            {**valid, "iss": "https://evil.example"},
            {"aud": CLIENT_ID},
        )
        for payload in invalid_payloads:
            with (
                self.subTest(payload=payload),
                patch.object(OIDCAuthenticationBackend, "verify_token", return_value=payload),
                self.assertRaises(SuspiciousOperation),
            ):
                backend.verify_token("id-token")
