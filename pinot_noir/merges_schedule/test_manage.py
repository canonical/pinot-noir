from datetime import time, timedelta

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django_tasks_db.models import DBTaskResult

from pinot_noir.data_manager.models import MergeBugFilterSettings, UserTokens, WeeklyTask
from pinot_noir.data_manager.tasks import schedule_weekly_tasks, submit_merge_bugs

from .tasks import refresh_merge_schedule

MERGE = MergeBugFilterSettings.TYPE_MERGE
BACKPORT = MergeBugFilterSettings.TYPE_BACKPORT
LP_CREDS = "[1]\nconsumer_key = x\n"


class ManagePageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", is_staff=True)
        self.client.force_login(self.user)
        self.url = reverse("site_admin:merges_schedule:index")

    def post(self, **data):
        return self.client.post(self.url, data, follow=True)

    def add(self, kind, field, value):
        return self.post(
            action="filter-add",
            settings_type=kind,
            field=field,
            **{f"{kind}-{field}-value": value},
        )

    def remove(self, kind, field, value):
        return self.post(action="filter-remove", settings_type=kind, field=field, value=value)

    def filter_settings(self, kind=MERGE):
        return MergeBugFilterSettings.objects.get(settings_type=kind)

    def give_token(self, user=None):
        UserTokens.objects.create(user=user or self.user, lp_token=LP_CREDS)

    def test_mounted_under_manage_with_page_slug(self):
        self.assertEqual(self.url, "/manage/merges-schedule/")

    def test_staff_only(self):
        self.client.force_login(User.objects.create_user("bob"))
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_nested_under_pages_in_side_nav(self):
        response = self.client.get(self.url)
        pages = next(s for s in response.context["site_admin_sections"] if s["label"] == "Pages")
        self.assertEqual(
            pages["children"],
            [{"label": "Merge Schedule", "url": self.url, "is_active": True}],
        )
        self.assertFalse(pages["is_active"])

    def test_renders_three_sections(self):
        response = self.client.get(self.url)
        for heading in ("Settings", "Schedule", "Commands"):
            self.assertContains(response, f">{heading}</h3>")

    # Settings

    def test_shows_entries_as_removable_chips(self):
        MergeBugFilterSettings.objects.create(
            site=Site.objects.get_current(),
            settings_type=MERGE,
            tags=["a-tag", "other"],
            subscribers=["someone"],
        )
        response = self.client.get(self.url)
        for value in ("a-tag", "other", "someone"):
            self.assertContains(response, f'<span class="p-chip__value">{value}</span>', html=True)
            self.assertContains(response, f'name="value" value="{value}"')
        self.assertContains(response, "None yet.", 2)  # both backport lists

    def test_add_entries_one_at_a_time(self):
        response = self.add(MERGE, "tags", " Merge-Tag ")
        self.assertContains(response, "Added merge-tag.")
        self.add(MERGE, "tags", "other")
        self.add(MERGE, "subscribers", "~Someone")
        merge = self.filter_settings()
        self.assertEqual((merge.tags, merge.subscribers), (["merge-tag", "other"], ["someone"]))
        self.assertEqual(merge.site, Site.objects.get_current())
        self.assertFalse(MergeBugFilterSettings.objects.filter(settings_type=BACKPORT).exists())

    def test_add_rejects_duplicates_and_bad_values(self):
        self.add(MERGE, "tags", "one")
        self.assertContains(self.add(MERGE, "tags", "ONE"), "one is already added.")
        self.assertContains(self.add(MERGE, "tags", "two words"), "Launchpad tags use")
        self.assertContains(self.add(MERGE, "tags", "a,b"), "Launchpad tags use")
        response = self.add(MERGE, "subscribers", "not/a/name")
        self.assertContains(response, "Enter a Launchpad user name.")
        self.assertEqual(
            (self.filter_settings().tags, self.filter_settings().subscribers), (["one"], [])
        )

    def test_subscribers_need_a_tag_first(self):
        response = self.add(BACKPORT, "subscribers", "someone")
        self.assertContains(response, "Add a tag first.")
        self.assertFalse(MergeBugFilterSettings.objects.exists())

    def test_remove_one_entry(self):
        for tag in ("one", "two", "three"):
            self.add(MERGE, "tags", tag)
        response = self.remove(MERGE, "tags", "two")
        self.assertContains(response, "Removed two.")
        self.assertEqual(self.filter_settings().tags, ["one", "three"])

    def test_last_tag_stays_while_subscribers_remain(self):
        self.add(MERGE, "tags", "one")
        self.add(MERGE, "subscribers", "someone")
        response = self.remove(MERGE, "tags", "one")
        self.assertContains(response, "Remove the subscribers before the last tag.")
        self.assertEqual(self.filter_settings().tags, ["one"])
        self.remove(MERGE, "subscribers", "someone")
        self.remove(MERGE, "tags", "one")
        self.assertFalse(MergeBugFilterSettings.objects.exists())

    def test_remove_missing_or_unknown(self):
        self.assertContains(self.remove(MERGE, "tags", "nope"), "nope isn&#x27;t in the list.")
        self.assertContains(self.remove("other", "tags", "x"), "Unknown setting.")
        self.assertContains(self.remove(MERGE, "site", "x"), "Unknown setting.")

    def test_model_rejects_non_lists(self):
        settings = MergeBugFilterSettings(
            site=Site.objects.get_current(), settings_type=MERGE, tags="a-tag", subscribers=[1]
        )
        with self.assertRaises(ValidationError) as caught:
            settings.full_clean()
        self.assertEqual(set(caught.exception.message_dict), {"tags"})
        settings.tags = ["a-tag"]
        with self.assertRaises(ValidationError) as caught:
            settings.full_clean()
        self.assertEqual(set(caught.exception.message_dict), {"subscribers"})

    # Commands

    def test_run_queues_task_as_current_user(self):
        self.give_token()
        response = self.post(action="run", task="refresh_merge_schedule")
        self.assertContains(response, "Queued: Refresh merge schedule.")
        result = DBTaskResult.objects.get(task_path=refresh_merge_schedule.module_path)
        self.assertEqual(result.args_kwargs["kwargs"], {"username": "alice"})

    def test_run_needs_lp_token(self):
        response = self.client.get(self.url)
        self.assertContains(response, "You need a Launchpad token")
        response = self.post(action="run", task="refresh_merge_schedule")
        self.assertContains(response, "Add your Launchpad token")
        self.assertFalse(DBTaskResult.objects.exists())

    def test_run_rejects_other_tasks(self):
        self.give_token()
        response = self.post(action="run", task="prune_task_results")
        self.assertContains(response, "Unknown command.")
        self.assertFalse(DBTaskResult.objects.exists())

    # Schedule

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
        self.add_schedule(**{"schedule-task": "prune_task_results"})
        self.assertFalse(WeeklyTask.objects.exists())

    def test_only_this_pages_tasks_listed(self):
        WeeklyTask.objects.create(task="refresh_reviews", time_of_day=time(1), user=self.user)
        WeeklyTask.objects.create(task="submit_merge_bugs", time_of_day=time(2), user=self.user)
        rows = self.client.get(self.url).context["schedule_rows"]
        self.assertEqual([row["task"].task for row in rows], ["submit_merge_bugs"])

    def test_flags_users_without_token(self):
        WeeklyTask.objects.create(task="submit_merge_bugs", time_of_day=time(2), user=self.user)
        self.assertContains(self.client.get(self.url), "No Launchpad token")
        self.give_token()
        self.assertNotContains(self.client.get(self.url), "No Launchpad token")

    def queued_weekly(self, task=submit_merge_bugs):
        run_at = timezone.now() + timedelta(days=1)
        task.using(run_after=run_at).enqueue(username="alice")
        return WeeklyTask.objects.create(
            task=task.name, time_of_day=time(2), user=self.user, monday=True, next_run=run_at
        )

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

    def test_remove_deletes_schedule_and_queued_run(self):
        weekly = self.queued_weekly()
        other_run = timezone.now() + timedelta(days=2)
        submit_merge_bugs.using(run_after=other_run).enqueue(username="alice")
        response = self.post(action="schedule-remove", id=weekly.pk)
        self.assertContains(response, "Removed a Submit merge bugs schedule.")
        self.assertFalse(WeeklyTask.objects.exists())
        self.assertEqual(
            list(DBTaskResult.objects.values_list("run_after", flat=True)), [other_run]
        )

    def test_cannot_touch_other_pages_schedules(self):
        weekly = WeeklyTask.objects.create(task="refresh_reviews", time_of_day=time(1))
        response = self.client.post(self.url, {"action": "schedule-remove", "id": weekly.pk})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(WeeklyTask.objects.exists())

    def test_scheduler_warning(self):
        self.assertContains(self.client.get(self.url), "scheduler isn't running")
        schedule_weekly_tasks.enqueue()
        self.assertNotContains(self.client.get(self.url), "scheduler isn't running")
