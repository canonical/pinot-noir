from unittest.mock import patch

from django.core.checks import run_checks
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from pinot_noir.data_manager.models import WeeklyTask
from pinot_noir.data_manager.tasks import get_schedulable_tasks

from .models import PageMetadata
from .registry import get_pages


class PageRegistryTests(TestCase):
    def test_pages_registered(self):
        self.assertEqual(
            [p.slug for p in get_pages()],
            ["merges-schedule", "reviews"],
        )

    def test_every_page_loads_and_is_in_nav(self):
        for page in get_pages():
            with self.subTest(page=page.slug):
                response = self.client.get(reverse(page.url_name))
                self.assertEqual(response.status_code, 200)
                slugs = [e["slug"] for e in response.context["nav_entries"]]
                self.assertEqual(slugs, [p.slug for p in get_pages()])

    def test_disabled_page_hidden_from_nav(self):
        PageMetadata.objects.update_or_create(slug="reviews", defaults={"enabled": False})
        response = self.client.get(reverse("merges_schedule:index"))
        self.assertNotIn("reviews", [e["slug"] for e in response.context["nav_entries"]])

    def test_page_checks_pass(self):
        errors = [e for e in run_checks() if (e.id or "").startswith("pages.")]
        self.assertEqual(errors, [])

    def test_refresh_tasks_schedulable(self):
        schedulable = get_schedulable_tasks()
        choices = dict(WeeklyTask.task_choices())
        for page in get_pages():
            with self.subTest(page=page.slug):
                self.assertIn(page.refresh_task_name, schedulable)
                self.assertIn(page.refresh_task_name, choices)
        self.assertEqual(set(schedulable), set(choices))


class RefreshPageCommandTests(TestCase):
    @patch("pinot_noir.pages.registry.Page.get_refresh_task")
    def test_enqueues_page_task(self, get_task):
        enqueue = get_task.return_value.enqueue
        call_command(
            "refresh_page", "reviews", "--username", "alice", stdout=open("/dev/null", "w")
        )
        enqueue.assert_called_once_with(username="alice")

    @patch("pinot_noir.pages.registry.Page.get_refresh_task")
    def test_passes_release(self, get_task):
        enqueue = get_task.return_value.enqueue
        call_command(
            "refresh_page",
            "merges-schedule",
            "--username",
            "alice",
            "--release",
            "resolute",
            stdout=open("/dev/null", "w"),
        )
        enqueue.assert_called_once_with(username="alice", release_adjective="resolute")
