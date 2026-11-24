from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django_tasks_db.models import DBTaskResult

from pinot_noir.data_manager.models import UserTokens

from .tasks import refresh_bug_triage

LP_CREDS = "[1]\nconsumer_key = x\n"


class BugTriageManageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", is_staff=True)
        self.client.force_login(self.user)
        self.url = reverse("site_admin:bug_triage:index")

    def post(self, **data):
        return self.client.post(self.url, data, follow=True)

    def test_mounted_under_manage_with_page_slug(self):
        self.assertEqual(self.url, "/manage/bug-triage/")

    def test_staff_only(self):
        self.client.force_login(User.objects.create_user("bob"))
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_renders_commands_without_shared_settings(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Commands")
        self.assertNotContains(response, "Default team")
        self.assertNotContains(response, 'id="ai-heading"')
        self.assertNotContains(response, "Agent tools")
        self.assertNotContains(response, ">Schedule</h3>")
        self.assertNotIn("schedule_form", response.context)

    def test_refresh_is_the_only_task(self):
        response = self.client.get(self.url)
        self.assertEqual([c.name for c in response.context["commands"]], [refresh_bug_triage.name])

    def test_run_refresh_uses_default_team(self):
        UserTokens.objects.create(user=self.user, lp_token=LP_CREDS)
        response = self.post(action="run", task=refresh_bug_triage.name)
        self.assertContains(response, "Queued: Refresh bug triage.")
        result = DBTaskResult.objects.get(task_path=refresh_bug_triage.module_path)
        # No team kwarg: the task uses the default team.
        self.assertEqual(result.args_kwargs["kwargs"], {"username": "alice"})
