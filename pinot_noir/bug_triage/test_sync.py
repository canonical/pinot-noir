from datetime import UTC, date, datetime
from unittest.mock import patch

import startriage.sources.launchpad.triage as lp_triage
from django.test import SimpleTestCase
from startriage.config import TeamConfig
from startriage.dates import triage_task_date_range
from startriage.source import TaskFilterOptions

from .sync import build_config, markdown_filename
from .tasks import _default_triage_day, _launchpad_credentials


def _opts(start: datetime, end: datetime) -> TaskFilterOptions:
    return TaskFilterOptions(
        team="server",
        start=start,
        end=end,
        recent_since=start,
        old_since=start,
        sources=frozenset(),
    )


class ConfigTests(SimpleTestCase):
    def test_build_config(self):
        team = TeamConfig(lp_team="ubuntu-server", lp_todo_tag="server-todo")
        config = build_config({"server": team}, default_team="server", github_token="")
        self.assertEqual(list(config.team), ["server"])
        self.assertEqual(config.general.default_team, "server")
        self.assertIsNone(config.general.github_token)

    def test_weekend_falls_back_to_friday(self):
        self.assertEqual(_default_triage_day(date(2026, 10, 17)), "friday")
        self.assertIsNone(_default_triage_day(date(2026, 10, 19)))


class MarkdownFilenameTests(SimpleTestCase):
    def test_single_day(self):
        start, end = triage_task_date_range("wednesday", today=date(2026, 10, 21))
        self.assertEqual(markdown_filename(_opts(start, end)), "triage-2026-10-20.md")

    def test_range(self):
        # Half-open: ends at 00:00 of the day after the last one.
        start = datetime(2026, 10, 16, tzinfo=UTC)
        end = datetime(2026, 10, 19, tzinfo=UTC)
        self.assertEqual(markdown_filename(_opts(start, end)), "triage-2026-10-16-2026-10-18.md")


class LaunchpadCredentialsTests(SimpleTestCase):
    def test_startriage_uses_given_token(self):
        original = lp_triage.connect_launchpad
        with (
            patch("pinot_noir.bug_triage.tasks.Credentials.from_string") as from_string,
            patch("pinot_noir.bug_triage.tasks.Launchpad") as launchpad,
            _launchpad_credentials("token-string"),
        ):
            self.assertIs(lp_triage.connect_launchpad(None), launchpad.return_value)
        from_string.assert_called_once_with("token-string")
        self.assertIs(lp_triage.connect_launchpad, original)
