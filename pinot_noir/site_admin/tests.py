from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from pinot_noir.data_manager.models import UserTokens

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
