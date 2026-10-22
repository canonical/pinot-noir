import hashlib

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from pinot_noir.data_manager.models import UserTokens
from pinot_noir.launchpad.models import LPUser
from pinot_noir.pages.models import PageMetadata
from pinot_noir.pages.registry import get_pages

LP = (
    "[1]\nconsumer_key = pinot-noir\nconsumer_secret = \n"
    "access_token = abc\naccess_secret = secret-def\n"
)


class TokensPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw", is_staff=True)
        self.client.force_login(self.user)
        self.url = reverse("site_admin:tokens")

    def post(self, **data):
        return self.client.post(self.url, data, follow=True)

    def test_requires_staff(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])
        User.objects.create_user("bob", password="pw")
        self.client.login(username="bob", password="pw")
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_index_redirects_to_tokens(self):
        self.assertRedirects(self.client.get(reverse("site_admin:index")), self.url)

    def test_never_renders_stored_tokens(self):
        UserTokens.objects.create(user=self.user, lp_token=LP, github_token="secret-gh")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "secret-gh")
        self.assertNotContains(response, "secret-def")
        self.assertContains(response, '<span class="p-chip__value">Set</span>', count=2)
        self.assertContains(response, '<span class="p-chip__value">Not set</span>', count=2)

    def test_sets_tokens_and_creates_row(self):
        response = self.post(lp_token=LP, github_token="gh", copilot_token="github_pat_x")
        self.assertContains(response, "Updated: Launchpad, GitHub, GitHub Copilot.")
        tokens = UserTokens.objects.get(user=self.user)
        self.assertEqual(
            (
                tokens.lp_token,
                tokens.github_token,
                tokens.copilot_token,
                tokens.openrouter_api_key,
            ),
            (LP.strip(), "gh", "github_pat_x", ""),
        )

    def test_blank_keeps_and_clear_removes(self):
        UserTokens.objects.create(user=self.user, github_token="gh", openrouter_api_key="or")
        self.post(clear_github_token="on")
        tokens = UserTokens.objects.get(user=self.user)
        self.assertEqual((tokens.github_token, tokens.openrouter_api_key), ("", "or"))

    def test_only_changes_own_tokens(self):
        other = User.objects.create_user("bob")
        UserTokens.objects.create(user=other, github_token="bob-gh")
        self.post(github_token="alice-gh")
        self.assertEqual(UserTokens.objects.get(user=other).github_token, "bob-gh")

    def test_rejects_bad_values(self):
        response = self.post(lp_token="nonsense", copilot_token="ghp_classic")
        self.assertContains(response, "not a Launchpad credentials string")
        self.assertContains(response, "does not accept classic tokens")
        self.assertFalse(UserTokens.objects.filter(user=self.user).exists())

    def test_set_and_remove_together_is_an_error(self):
        UserTokens.objects.create(user=self.user, github_token="gh")
        response = self.post(github_token="new", clear_github_token="on")
        self.assertContains(response, "not both")
        self.assertEqual(UserTokens.objects.get(user=self.user).github_token, "gh")

    def test_sidebar_link_only_for_staff(self):
        manage = reverse("site_admin:index")
        self.assertContains(self.client.get(reverse("merges_schedule:index")), f'href="{manage}"')
        self.client.logout()
        self.assertNotContains(
            self.client.get(reverse("merges_schedule:index")), f'href="{manage}"'
        )


class PagesSectionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", is_staff=True)
        self.client.force_login(self.user)
        self.url = reverse("site_admin:pages")

    def test_requires_staff(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_lists_registered_pages(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for page in get_pages():
            self.assertContains(response, f'value="{page.slug}"')

    def test_disable_and_enable(self):
        keep = {p.slug for p in get_pages()} - {"reviews"}
        response = self.client.post(self.url, {"enabled": sorted(keep)}, follow=True)
        self.assertContains(response, "Reviews disabled.")
        self.assertFalse(PageMetadata.objects.get(slug="reviews").enabled)
        self.assertNotContains(
            self.client.get(reverse("merges_schedule:index")), 'href="/reviews"'
        )

        response = self.client.post(self.url, {"enabled": sorted(keep | {"reviews"})}, follow=True)
        self.assertContains(response, "Reviews enabled.")
        self.assertTrue(PageMetadata.objects.get(slug="reviews").enabled)

    def test_no_change(self):
        response = self.client.post(
            self.url, {"enabled": [p.slug for p in get_pages()]}, follow=True
        )
        self.assertContains(response, "No pages changed.")


class TogglePageTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user("alice", is_staff=True))

    def toggle(self, slug, enabled):
        url = reverse("site_admin:toggle-page", args=[slug])
        return self.client.post(url, {"enabled": "true" if enabled else "false"})

    def test_toggles_one_page(self):
        response = self.toggle("reviews", False)
        self.assertEqual(response.json(), {"slug": "reviews", "enabled": False})
        self.assertFalse(PageMetadata.objects.get(slug="reviews").enabled)
        self.assertTrue(PageMetadata.objects.get(slug="bug-triage").enabled)
        self.assertEqual(self.toggle("reviews", True).json()["enabled"], True)

    def test_unknown_page_and_get(self):
        self.assertEqual(self.toggle("nope", False).status_code, 404)
        url = reverse("site_admin:toggle-page", args=["reviews"])
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_requires_staff(self):
        self.client.logout()
        self.assertEqual(self.toggle("reviews", False).status_code, 302)
        self.assertTrue(PageMetadata.objects.get(slug="reviews").enabled)

    def test_nav_items_carry_slugs(self):
        response = self.client.get(reverse("site_admin:pages"))
        self.assertContains(response, 'data-page-slug="reviews"')
        self.assertContains(response, "data-site-admin-nav")


class TeamPageTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user("alice", is_staff=True))
        self.url = reverse("site_admin:team")

    def add(self, role, prefix, username, email=""):
        data = {"role": role, f"{prefix}-username": username, f"{prefix}-email": email}
        return self.client.post(self.url, data, follow=True)

    def remove(self, role, username):
        data = {"role": role, "action": "remove", "username": username}
        return self.client.post(self.url, data, follow=True)

    def test_requires_staff(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_two_tables(self):
        LPUser.objects.create(username="lvoytek", is_team_member=True)
        LPUser.objects.create(username="ubuntu-server", is_review_marker=True)
        LPUser.objects.create(username="someone")
        response = self.client.get(self.url)
        team, markers = response.context["tables"]
        self.assertEqual([u.username for u in team["users"]], ["lvoytek"])
        self.assertEqual([u.username for u in markers["users"]], ["ubuntu-server"])
        self.assertNotContains(response, "~someone")

    def test_add_team_member_with_email(self):
        response = self.add("is_team_member", "team", "~LVoytek", "Lena@Example.com")
        self.assertContains(response, "Added lvoytek to team members.")
        user = LPUser.objects.get(username="lvoytek")
        self.assertTrue(user.is_team_member)
        self.assertFalse(user.is_review_marker)
        self.assertEqual(user.email_md5, hashlib.md5(b"lena@example.com").hexdigest())

    def test_add_existing_user_keeps_other_role(self):
        LPUser.objects.create(username="lvoytek", is_team_member=True, email_md5="x" * 32)
        self.add("is_review_marker", "marker", "lvoytek")
        user = LPUser.objects.get(username="lvoytek")
        self.assertTrue(user.is_team_member and user.is_review_marker)
        self.assertEqual(user.email_md5, "x" * 32)
        response = self.add("is_review_marker", "marker", "lvoytek")
        self.assertContains(response, "already in review markers")

    def test_remove_clears_only_that_role(self):
        LPUser.objects.create(username="lvoytek", is_team_member=True, is_review_marker=True)
        response = self.remove("is_team_member", "lvoytek")
        self.assertContains(response, "Removed lvoytek from team members.")
        user = LPUser.objects.get(username="lvoytek")
        self.assertFalse(user.is_team_member)
        self.assertTrue(user.is_review_marker)

    def test_review_markers_have_no_email(self):
        response = self.client.get(self.url)
        self.assertContains(response, 'name="team-email"')
        self.assertNotContains(response, 'name="marker-email"')
        self.add("is_review_marker", "marker", "some-team", "ignored@example.com")
        self.assertIsNone(LPUser.objects.get(username="some-team").email_md5)

    def test_invalid_username_shows_error_in_its_table(self):
        response = self.add("is_review_marker", "marker", "not a name")
        self.assertContains(response, "Enter a Launchpad user name")
        self.assertTrue(response.context["tables"][1]["form"].errors)
        self.assertFalse(response.context["tables"][0]["form"].is_bound)
        self.assertFalse(LPUser.objects.exists())

    def test_unknown_role_is_ignored(self):
        self.client.post(self.url, {"role": "is_superuser", "action": "remove", "username": "x"})
        self.assertFalse(LPUser.objects.exists())
