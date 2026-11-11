from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class FrontendAuthenticationTests(TestCase):
    def setUp(self):
        self.password = "a-secure-test-password"
        self.user = User.objects.create_user("alice", password=self.password, is_staff=True)
        self.login_url = reverse("login")
        self.manage_url = reverse("site_admin:index")

    def test_admin_redirects_to_frontend_login(self):
        response = self.client.get(self.manage_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{self.login_url}?next={self.manage_url}")
        response = self.client.get(response["Location"])
        self.assertContains(response, f'action="{self.login_url}"')
        self.assertContains(response, f'name="next" value="{self.manage_url}"')

    def test_sidebar_separates_login_or_logout_from_pages(self):
        page_url = reverse("merges_schedule:index")
        response = self.client.get(page_url)
        self.assertContains(response, f'href="{self.login_url}"')
        self.assertContains(response, 'aria-label="Account"', count=1)
        self.assertContains(response, '<hr class="p-rule--muted">', count=1)
        self.assertNotContains(response, f'action="{reverse("logout")}"')

        self.client.force_login(self.user)
        response = self.client.get(page_url)
        self.assertNotContains(response, f'href="{self.login_url}"')
        self.assertContains(response, f'action="{reverse("logout")}"')
        self.assertContains(response, "Log out")
        content = response.content.decode()
        main_nav = content.split('<nav aria-label="Main">', 1)[1].split("</nav>", 1)[0]
        account_nav = content.split('<nav aria-label="Account"', 1)[1].split("</nav>", 1)[0]
        self.assertNotIn("data-site-admin-nav", main_nav)
        self.assertIn("data-site-admin-nav", account_nav)
        self.assertIn("data-user-settings-nav", account_nav)

    def test_login_returns_to_requested_admin_page(self):
        response = self.client.post(
            self.login_url,
            {
                "username": self.user.username,
                "password": self.password,
                "next": self.manage_url,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.manage_url)
        response = self.client.get(response["Location"], follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My team")
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_non_staff_user_can_log_in(self):
        user = User.objects.create_user("bob", password=self.password)
        page_url = reverse("merges_schedule:index")
        response = self.client.post(
            self.login_url,
            {
                "username": user.username,
                "password": self.password,
                "next": page_url,
            },
        )
        self.assertRedirects(response, page_url)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)
        response = self.client.get(page_url)
        self.assertContains(response, "Log out")
        self.assertContains(response, "data-user-settings-nav")
        self.assertNotContains(response, f'href="{self.manage_url}"')

    def test_login_defaults_to_frontend(self):
        response = self.client.post(
            self.login_url,
            {"username": self.user.username, "password": self.password},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("root-redirect"))
        response = self.client.get(response["Location"], follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Log out")

    def test_invalid_login_shows_error(self):
        response = self.client.post(
            self.login_url,
            {"username": self.user.username, "password": "wrong"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a correct username and password")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_requires_post_and_returns_to_frontend(self):
        self.client.force_login(self.user)
        logout_url = reverse("logout")
        self.assertEqual(self.client.get(logout_url).status_code, 405)

        response = self.client.post(logout_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("root-redirect"))
        self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.get(response["Location"], follow=True)
        self.assertContains(response, f'href="{self.login_url}"')
