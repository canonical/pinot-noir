from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django_tasks_db.models import DBTaskResult

from pinot_noir.data_manager.models import UserTokens, WeeklyTask
from pinot_noir.data_manager.tasks import schedule_weekly_tasks, submit_merge_bugs
from pinot_noir.reviews.tasks import refresh_reviews

LP_CREDS = "[1]\nconsumer_key = x\n"


class TaskScheduleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", is_staff=True)
        self.client.force_login(self.user)
        self.url = reverse("site_admin:task-schedule")

    def post(self, **data):
        return self.client.post(self.url, data, follow=True)

    def add_schedule(self, **overrides):
        data = {
            "action": "schedule-add",
            "schedule-task": "submit_merge_bugs",
            "schedule-time_of_day": "09:30",
            "schedule-user": str(self.user.pk),
            "schedule-days": ["monday", "thursday"],
        }
        data.update(overrides)
        return self.post(**data)

    def queued_weekly(self, task=submit_merge_bugs):
        run_at = timezone.now() + timedelta(days=1)
        task.using(run_after=run_at).enqueue(username="alice")
        return WeeklyTask.objects.create(
            task=task.name, time_of_day=time(2), user=self.user, monday=True, next_run=run_at
        )

    def test_requires_staff(self):
        self.client.force_login(User.objects.create_user("bob"))
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_appears_in_admin_navigation(self):
        response = self.client.get(self.url)
        sections = response.context["site_admin_sections"]
        self.assertEqual(
            [section["label"] for section in sections],
            ["My team", "Startriage", "Task Schedule", "Pages"],
        )
        self.assertEqual(self.url, "/manage/task-schedule")
        self.assertTrue(sections[2]["is_active"])

    def test_one_form_offers_every_schedulable_task(self):
        response = self.client.get(self.url)
        form = response.context["schedule_form"]
        self.assertEqual(list(form.fields["task"].choices), WeeklyTask.task_choices())
        self.assertContains(response, 'name="action" value="schedule-add"', count=1)
        for _, label in WeeklyTask.task_choices():
            self.assertContains(response, label)

    def test_lists_schedules_from_all_pages_and_base_tasks(self):
        WeeklyTask.objects.create(task="refresh_reviews", time_of_day=time(1), user=self.user)
        WeeklyTask.objects.create(task="submit_merge_bugs", time_of_day=time(2), user=self.user)
        WeeklyTask.objects.create(task="prune_task_results", time_of_day=time(3))
        response = self.client.get(self.url)
        rows = response.context["schedule_rows"]
        self.assertEqual(
            [row["task"].task for row in rows],
            ["refresh_reviews", "submit_merge_bugs", "prune_task_results"],
        )
        self.assertEqual(
            [row["label"] for row in rows],
            ["Refresh reviews", "Submit merge bugs", "Prune task results"],
        )

    def test_add_schedule(self):
        response = self.add_schedule()
        self.assertContains(response, "Scheduled Submit merge bugs.")
        weekly = WeeklyTask.objects.get()
        self.assertEqual(
            (weekly.task, weekly.time_of_day, weekly.user, weekly.enabled),
            ("submit_merge_bugs", time(9, 30), self.user, True),
        )
        self.assertEqual(weekly.active_days_display(), "Monday, Thursday")

    def test_add_schedule_needs_days_and_known_task(self):
        response = self.add_schedule(**{"schedule-days": []})
        self.assertContains(response, "This field is required.")
        response = self.add_schedule(**{"schedule-task": "not_a_task"})
        self.assertContains(response, "Select a valid choice.")
        self.assertFalse(WeeklyTask.objects.exists())

    def test_flags_users_without_token(self):
        WeeklyTask.objects.create(task="submit_merge_bugs", time_of_day=time(2), user=self.user)
        self.assertContains(self.client.get(self.url), "No Launchpad token")
        UserTokens.objects.create(user=self.user, lp_token=LP_CREDS)
        self.assertNotContains(self.client.get(self.url), "No Launchpad token")

    def test_pause_and_resume_cancel_queued_run(self):
        weekly = self.queued_weekly()
        response = self.post(action="schedule-pause", id=weekly.pk)
        self.assertContains(response, "Paused a Submit merge bugs schedule.")
        weekly.refresh_from_db()
        self.assertEqual((weekly.enabled, weekly.next_run), (False, None))
        self.assertFalse(DBTaskResult.objects.exists())
        self.post(action="schedule-resume", id=weekly.pk)
        weekly.refresh_from_db()
        self.assertTrue(weekly.enabled)

    def test_remove_deletes_schedule_and_only_its_queued_run(self):
        weekly = self.queued_weekly()
        other_weekly = WeeklyTask.objects.create(
            task="refresh_reviews", time_of_day=time(3), user=self.user
        )
        other_run = timezone.now() + timedelta(days=2)
        submit_merge_bugs.using(run_after=other_run).enqueue(username="alice")
        response = self.post(action="schedule-remove", id=weekly.pk)
        self.assertContains(response, "Removed a Submit merge bugs schedule.")
        self.assertEqual(list(WeeklyTask.objects.all()), [other_weekly])
        self.assertEqual(
            list(DBTaskResult.objects.values_list("run_after", flat=True)), [other_run]
        )

    def test_can_pause_another_pages_schedule(self):
        weekly = WeeklyTask.objects.create(
            task=refresh_reviews.name, time_of_day=time(1), user=self.user
        )
        response = self.post(action="schedule-pause", id=weekly.pk)
        self.assertContains(response, "Paused a Refresh reviews schedule.")
        weekly.refresh_from_db()
        self.assertFalse(weekly.enabled)

    def test_unknown_schedule_is_404_and_leaves_other_rows_untouched(self):
        weekly = WeeklyTask.objects.create(task="refresh_reviews", time_of_day=time(1))
        response = self.client.post(self.url, {"action": "schedule-remove", "id": weekly.pk + 1})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(WeeklyTask.objects.filter(pk=weekly.pk).exists())

    def test_scheduler_warning(self):
        self.assertContains(self.client.get(self.url), "scheduler isn't running")
        schedule_weekly_tasks.enqueue()
        self.assertNotContains(self.client.get(self.url), "scheduler isn't running")

    def test_run_actions_stay_on_command_pages(self):
        response = self.post(action="run", task=submit_merge_bugs.name)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DBTaskResult.objects.exists())
