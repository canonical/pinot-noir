from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from pinot_noir.data_manager.models import UserTokens

from .models import Preferences

LP = (
    "[1]\nconsumer_key = pinot-noir\nconsumer_secret = \n"
    "access_token = abc\naccess_secret = secret-def\n"
)


class GeneralSettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")
        self.client.force_login(self.user)
        self.url = reverse("user_settings:general")

    def post(self, theme):
        return self.client.post(self.url, {"theme": theme}, follow=True)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response["Location"], f"{reverse('login')}?next={self.url}")

    def test_general_is_first_section_and_defaults_to_light(self):
        response = self.client.get(self.url)
        self.assertEqual(
            [section["label"] for section in response.context["user_settings_sections"]],
            ["General", "My tokens"],
        )
        self.assertEqual(response.context["form"]["theme"].value(), Preferences.Theme.LIGHT)
        self.assertContains(response, '<body class="is-light">')
        self.assertContains(response, "Appearance")
        self.assertContains(response, "Light")
        self.assertContains(response, "Dark")
        self.assertContains(response, 'class="p-radio__input"', count=2)

    def test_dark_and_light_preferences_apply_to_all_pages(self):
        response = self.post(Preferences.Theme.DARK)
        self.assertContains(response, "Appearance set to Dark.")
        self.assertContains(response, '<body class="is-dark">')
        self.assertEqual(Preferences.objects.get(user=self.user).theme, Preferences.Theme.DARK)
        response = self.client.get(reverse("merges_schedule:index"))
        self.assertContains(response, '<body class="is-dark">')
        self.assertContains(response, "p-icon--user is-light")
        self.assertContains(response, 'class="p-panel is-dark"', count=2)

        response = self.post(Preferences.Theme.LIGHT)
        self.assertContains(response, "Appearance set to Light.")
        self.assertContains(response, '<body class="is-light">')
        self.assertEqual(Preferences.objects.get(user=self.user).theme, Preferences.Theme.LIGHT)
        response = self.client.get(reverse("merges_schedule:index"))
        self.assertContains(response, '<body class="is-light">')
        self.assertContains(response, "p-icon--user is-light")
        self.assertContains(response, 'class="p-panel is-dark"', count=2)

    def test_only_changes_own_preferences(self):
        other = User.objects.create_user("bob")
        Preferences.objects.create(user=other, theme=Preferences.Theme.LIGHT)
        self.post(Preferences.Theme.DARK)
        self.assertEqual(Preferences.objects.get(user=self.user).theme, Preferences.Theme.DARK)
        self.assertEqual(Preferences.objects.get(user=other).theme, Preferences.Theme.LIGHT)

    def test_rejects_unknown_theme(self):
        response = self.post("sepia")
        self.assertContains(response, "Select a valid choice")
        self.assertFalse(Preferences.objects.filter(user=self.user).exists())


class TokensPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="pw")
        self.client.force_login(self.user)
        self.url = reverse("user_settings:tokens")

    def post(self, **data):
        return self.client.post(self.url, data, follow=True)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], f"{reverse('login')}?next={self.url}")

    def test_non_staff_user_can_use_settings(self):
        response = self.client.get(reverse("user_settings:index"))
        self.assertRedirects(response, reverse("user_settings:general"))
        response = self.client.get(self.url)
        self.assertContains(response, "Settings")
        self.assertContains(response, "General")
        self.assertContains(response, "My tokens")
        self.assertContains(response, "Signed in as alice")
        self.assertContains(response, 'aria-label="User settings sections"')
        self.assertNotContains(response, "Django admin")

    def test_settings_link_available_without_staff_permission(self):
        response = self.client.get(reverse("merges_schedule:index"))
        self.assertContains(response, "data-user-settings-nav")
        self.assertContains(response, f'href="{reverse("user_settings:index")}"')
        self.assertNotContains(response, "data-site-admin-nav")
        self.client.logout()
        response = self.client.get(reverse("merges_schedule:index"))
        self.assertNotContains(response, "data-user-settings-nav")

    def test_old_admin_tokens_url_redirects_to_user_settings(self):
        response = self.client.get("/manage/tokens")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.url)
        self.assertEqual(self.client.get(response["Location"]).status_code, 200)

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
