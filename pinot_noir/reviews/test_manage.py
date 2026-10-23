from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django_tasks_db.models import DBTaskResult

from pinot_noir.data_manager.models import UserTokens
from pinot_noir.launchpad.models import LPUser

from .tasks import refresh_reviews

LP_CREDS = "[1]\nconsumer_key = x\n"


class ReviewsManageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", is_staff=True)
        self.client.force_login(self.user)
        self.url = reverse("site_admin:reviews:index")

    def add(self, username, email=""):
        data = {"role": "is_review_marker", "marker-username": username, "marker-email": email}
        return self.client.post(self.url, data, follow=True)

    def test_mounted_under_manage_with_page_slug(self):
        self.assertEqual(self.url, "/manage/reviews/")

    def test_staff_only(self):
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_renders_three_sections_and_markers_only(self):
        LPUser.objects.create(username="lvoytek", is_team_member=True)
        LPUser.objects.create(username="ubuntu-server", is_review_marker=True)
        response = self.client.get(self.url)
        for heading in ("Settings", "Schedule", "Commands", "Review markers"):
            self.assertContains(response, heading)
        (markers,) = response.context["tables"]
        self.assertEqual([u.username for u in markers["users"]], ["ubuntu-server"])
        self.assertNotContains(response, 'name="team-username"')

    def test_add_marker_keeps_other_role(self):
        LPUser.objects.create(username="lvoytek", is_team_member=True, email_md5="x" * 32)
        response = self.add("~LVoytek")
        self.assertContains(response, "Added lvoytek to review markers.")
        self.assertRedirects(response, self.url)
        user = LPUser.objects.get(username="lvoytek")
        self.assertTrue(user.is_team_member and user.is_review_marker)
        self.assertEqual(user.email_md5, "x" * 32)
        self.assertContains(self.add("lvoytek"), "already in review markers")

    def test_markers_have_no_email(self):
        response = self.client.get(self.url)
        self.assertNotContains(response, 'name="marker-email"')
        self.add("some-team", "ignored@example.com")
        self.assertIsNone(LPUser.objects.get(username="some-team").email_md5)

    def test_invalid_username(self):
        response = self.add("not a name")
        self.assertContains(response, "Enter a Launchpad user name")
        self.assertTrue(response.context["tables"][0]["form"].errors)
        self.assertFalse(LPUser.objects.exists())

    def test_remove_clears_only_marker(self):
        LPUser.objects.create(username="lvoytek", is_team_member=True, is_review_marker=True)
        data = {"role": "is_review_marker", "action": "remove", "username": "lvoytek"}
        response = self.client.post(self.url, data, follow=True)
        self.assertContains(response, "Removed lvoytek from review markers.")
        user = LPUser.objects.get(username="lvoytek")
        self.assertFalse(user.is_review_marker)
        self.assertTrue(user.is_team_member)

    def test_team_member_posts_are_ignored_here(self):
        data = {"role": "is_team_member", "team-username": "lvoytek"}
        self.client.post(self.url, data)
        self.assertFalse(LPUser.objects.exists())

    def test_refresh_reviews_is_the_only_task(self):
        response = self.client.get(self.url)
        self.assertEqual([c.name for c in response.context["commands"]], [refresh_reviews.name])
        choices = [value for value, _ in response.context["schedule_form"].fields["task"].choices]
        self.assertEqual([c for c in choices if c], [refresh_reviews.name])

    def test_run_refresh(self):
        UserTokens.objects.create(user=self.user, lp_token=LP_CREDS)
        data = {"action": "run", "task": refresh_reviews.name}
        response = self.client.post(self.url, data, follow=True)
        self.assertContains(response, "Queued: Refresh reviews.")
        result = DBTaskResult.objects.get(task_path=refresh_reviews.module_path)
        self.assertEqual(result.args_kwargs["kwargs"], {"username": "alice"})

    def test_schedule_refresh(self):
        data = {
            "action": "schedule-add",
            "schedule-task": refresh_reviews.name,
            "schedule-time_of_day": "06:00",
            "schedule-user": self.user.pk,
            "schedule-days": ["monday"],
        }
        response = self.client.post(self.url, data, follow=True)
        self.assertContains(response, "Scheduled Refresh reviews.")
