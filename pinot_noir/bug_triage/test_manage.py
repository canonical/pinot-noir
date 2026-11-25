from datetime import UTC, datetime, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django_tasks_db.models import DBTaskResult

from pinot_noir.data_manager.models import UserTokens

from .models import StartriageAISettings, TriageReport, TriageSettings
from .tasks import refresh_bug_triage

LP_CREDS = "[1]\nconsumer_key = x\n"


def _report(html: str, days: int = 0) -> TriageReport:
    report = TriageReport.objects.create(
        team="server",
        start=datetime(2026, 10, 20, tzinfo=UTC) - timedelta(days=days),
        end=datetime(2026, 10, 21, tzinfo=UTC) - timedelta(days=days),
        html=html,
    )
    TriageReport.objects.filter(pk=report.pk).update(
        generated_at=timezone.now() - timedelta(days=days)
    )
    return report


class BugTriageManageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", is_staff=True)
        self.client.force_login(self.user)
        self.url = reverse("site_admin:bug_triage:index")

    def post(self, **data):
        return self.client.post(self.url, data, follow=True)

    def history_data(self, **overrides):
        data = {
            "action": "history-settings",
            "history-retention_days": "7",
        }
        data.update(overrides)
        return data

    def test_mounted_under_manage_with_page_slug(self):
        self.assertEqual(self.url, "/manage/bug-triage/")

    def test_staff_only(self):
        self.client.force_login(User.objects.create_user("bob"))
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_renders_report_history_and_commands_without_shared_settings(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Settings")
        self.assertContains(response, 'id="history-heading"')
        self.assertContains(response, "Report history")
        self.assertContains(response, "Commands")
        self.assertNotContains(response, "Default team")
        self.assertNotContains(response, 'id="ai-heading"')
        self.assertNotContains(response, "Agent tools")
        self.assertNotContains(response, ">Schedule</h3>")
        self.assertNotIn("schedule_form", response.context)

    def test_report_history_defaults(self):
        response = self.client.get(self.url)
        form = response.context["history_form"]
        self.assertEqual(form.instance.retention_days, 7)
        self.assertEqual(list(form.fields), ["retention_days"])
        self.assertFalse(TriageSettings.objects.exists())

    def test_save_report_history_settings_and_prune(self):
        _report("expired", 8)
        _report("previous", 2)
        _report("current")
        ai = StartriageAISettings.objects.create(provider="copilot", model="gpt-5")
        response = self.post(**self.history_data(**{"history-retention_days": "1"}))
        self.assertContains(response, "Saved the report history settings.")
        settings = TriageSettings.objects.get()
        self.assertEqual(settings.retention_days, 1)
        self.assertEqual(list(TriageReport.objects.values_list("html", flat=True)), ["current"])
        self.assertTrue(StartriageAISettings.objects.filter(pk=ai.pk).exists())
        self.assertFalse(DBTaskResult.objects.exists())

    def test_report_history_validation_keeps_settings_and_reports(self):
        _report("current")
        response = self.post(**self.history_data(**{"history-retention_days": "0"}))
        self.assertContains(response, "Ensure this value is greater than or equal to 1.")
        self.assertFalse(TriageSettings.objects.exists())
        self.assertEqual(TriageReport.objects.get().html, "current")

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
