from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django_tasks_db.models import DBTaskResult

from pinot_noir.data_manager.models import UserTokens

from .models import HousekeepingSettings
from .tasks import refresh_bug_housekeeping

LP_CREDS = "[1]\nconsumer_key = x\n"


class BugHousekeepingManageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", is_staff=True)
        self.client.force_login(self.user)
        self.url = reverse("site_admin:bug_housekeeping:index")

    def post(self, **data):
        return self.client.post(self.url, data, follow=True)

    def settings_data(self, **overrides):
        data = {
            "action": "git-settings",
            "git-repository": "git@example.com:team/saved-bugs.git",
            "git-working_directory": "data/bug-housekeeping",
        }
        data.update(overrides)
        return data

    def test_mounted_and_staff_only(self):
        self.assertEqual(self.url, "/manage/bug-housekeeping/")
        self.client.force_login(User.objects.create_user("bob"))
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_renders_sections(self):
        response = self.client.get(self.url)
        for heading in ("Settings", "Schedule", "Commands"):
            self.assertContains(response, heading)
        self.assertContains(response, "Create settings")
        self.assertContains(response, "default team configured in Bug Triage")

    def test_create_and_edit_git_settings(self):
        response = self.post(**self.settings_data())
        self.assertContains(response, "Saved the Git repository settings.")
        settings = HousekeepingSettings.objects.get()
        self.assertEqual(settings.repository, "git@example.com:team/saved-bugs.git")
        self.assertEqual(settings.working_directory, "data/bug-housekeeping")

        self.post(**self.settings_data(**{"git-working_directory": "/srv/pinot-noir/saved-bugs"}))
        self.assertEqual(HousekeepingSettings.objects.count(), 1)
        self.assertEqual(
            HousekeepingSettings.objects.get().working_directory,
            "/srv/pinot-noir/saved-bugs",
        )

    def test_rejects_missing_repository_and_non_dedicated_checkout(self):
        response = self.post(**self.settings_data(**{"git-repository": ""}))
        self.assertContains(response, "This field is required.")
        response = self.post(**self.settings_data(**{"git-working_directory": "."}))
        self.assertContains(response, "Choose a dedicated subdirectory")
        self.assertFalse(HousekeepingSettings.objects.exists())

    def test_refresh_is_the_only_task(self):
        response = self.client.get(self.url)
        self.assertEqual(
            [command.name for command in response.context["commands"]],
            [refresh_bug_housekeeping.name],
        )
        choices = [value for value, _ in response.context["schedule_form"].fields["task"].choices]
        self.assertEqual([choice for choice in choices if choice], [refresh_bug_housekeeping.name])

    def test_run_refresh_uses_default_team(self):
        UserTokens.objects.create(user=self.user, lp_token=LP_CREDS)
        response = self.post(action="run", task=refresh_bug_housekeeping.name)
        self.assertContains(response, "Queued: Refresh bug housekeeping.")
        result = DBTaskResult.objects.get(task_path=refresh_bug_housekeeping.module_path)
        self.assertEqual(result.args_kwargs["kwargs"], {"username": "alice"})
