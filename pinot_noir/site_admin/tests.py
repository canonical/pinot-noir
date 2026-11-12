import hashlib

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.test import TestCase
from django.urls import reverse

from pinot_noir.data_manager.models import TeamSettings
from pinot_noir.launchpad.models import ReviewMarker
from pinot_noir.pages.models import PageMetadata
from pinot_noir.pages.registry import get_pages


class AdminNavigationTests(TestCase):
    def test_sidebar_link_only_for_staff(self):
        self.client.force_login(User.objects.create_user("alice", is_staff=True))
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
        self.user = User.objects.create_user("alice", email="Alice@Example.com", is_staff=True)
        self.client.force_login(self.user)
        self.url = reverse("site_admin:team")

    def test_index_redirects_to_team(self):
        self.assertRedirects(self.client.get(reverse("site_admin:index")), self.url)

    def add(self, username, email=""):
        data = {"role": "team", "team-username": username, "team-email": email}
        return self.client.post(self.url, data, follow=True)

    def remove(self, username):
        data = {"role": "team", "action": "remove", "username": username}
        return self.client.post(self.url, data, follow=True)

    def test_requires_staff(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_lists_active_django_users_only(self):
        User.objects.create_user("lvoytek")
        User.objects.create_user("inactive", is_active=False)
        response = self.client.get(self.url)
        (team,) = response.context["tables"]
        self.assertEqual([u.username for u in team["users"]], ["alice", "lvoytek"])
        self.assertNotContains(response, "inactive")
        self.assertNotContains(response, 'name="marker-username"')

    def test_add_team_member_with_email(self):
        response = self.add("~LVoytek", "Lena@Example.com")
        self.assertContains(response, "Added lvoytek to team members.")
        user = User.objects.get(username="lvoytek")
        self.assertTrue(user.is_active)
        self.assertEqual(user.email, "Lena@example.com")
        self.assertFalse(user.has_usable_password())

    def test_gravatar_is_generated_from_normalized_django_email(self):
        response = self.client.get(self.url)
        email_hash = hashlib.md5(b"alice@example.com", usedforsecurity=False).hexdigest()
        self.assertContains(response, f"https://www.gravatar.com/avatar/{email_hash}?s=32")

    def test_invalid_username_shows_error(self):
        response = self.add("not a name")
        self.assertContains(response, "Enter a Launchpad user name")
        self.assertEqual(User.objects.count(), 1)

    def test_review_marker_posts_are_ignored_here(self):
        self.client.post(self.url, {"role": "review-marker", "marker-username": "some-team"})
        self.assertEqual(User.objects.count(), 1)

    def test_remove_deactivates_user_without_removing_review_marker(self):
        user = User.objects.create_user("lvoytek")
        ReviewMarker.objects.create(username="lvoytek")
        response = self.remove("lvoytek")
        self.assertContains(response, "Deactivated lvoytek.")
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertTrue(ReviewMarker.objects.filter(username="lvoytek").exists())

    def test_cannot_deactivate_own_account(self):
        response = self.remove("alice")
        self.assertContains(response, "You cannot deactivate your own account.")
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_add_reactivates_user_and_updates_email_without_resetting_password(self):
        user = User.objects.create_user(
            "lvoytek", email="old@example.com", password="pw", is_active=False
        )
        response = self.add("LVoytek", "new@example.com")
        self.assertContains(response, "Added lvoytek to team members.")
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(user.email, "new@example.com")
        self.assertTrue(user.check_password("pw"))

    def test_existing_active_user_email_can_be_updated(self):
        user = User.objects.create_user("lvoytek", email="old@example.com")
        response = self.add("lvoytek", "new@example.com")
        self.assertContains(response, "lvoytek is already in team members.")
        user.refresh_from_db()
        self.assertEqual(user.email, "new@example.com")

    def test_unknown_role_is_ignored(self):
        self.client.post(self.url, {"role": "is_superuser", "action": "remove", "username": "x"})
        self.assertEqual(User.objects.count(), 1)


class TeamNameTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user("alice", is_staff=True))
        self.url = reverse("site_admin:team")

    def set_name(self, name):
        data = {"action": "team-name", "settings-name": name}
        return self.client.post(self.url, data, follow=True)

    def test_header_defaults_to_pinot_noir(self):
        response = self.client.get(reverse("merges_schedule:index"))
        self.assertContains(
            response, '<span class="p-navigation__logo-title">Pinot Noir</span>', 2
        )

    def test_set_name_replaces_header(self):
        response = self.set_name("  Server Team ")
        self.assertContains(response, "Team name set to Server Team.")
        settings = TeamSettings.objects.get(site=Site.objects.get_current())
        self.assertEqual(settings.name, "Server Team")
        response = self.client.get(reverse("merges_schedule:index"))
        self.assertContains(
            response, '<span class="p-navigation__logo-title">Server Team</span>', 2
        )
        self.assertNotContains(response, 'logo-title">Pinot Noir')

    def test_clearing_name_restores_default(self):
        self.set_name("Server Team")
        response = self.set_name("")
        self.assertContains(response, "Team name cleared.")
        self.assertContains(
            response, '<span class="p-navigation__logo-title">Pinot Noir</span>', 2
        )
        self.assertEqual(TeamSettings.objects.count(), 1)

    def test_name_form_does_not_touch_users(self):
        user = User.objects.create_user("someone", is_active=False)
        self.set_name("Server Team")
        user.refresh_from_db()
        self.assertFalse(user.is_active)

    def test_settings_are_per_site(self):
        other = Site.objects.create(domain="other.example", name="other")
        TeamSettings.objects.create(site=other, name="Other Team")
        self.assertEqual(TeamSettings.current().name, "")
        with self.settings(SITE_ID=other.pk):
            self.assertEqual(TeamSettings.current().name, "Other Team")
