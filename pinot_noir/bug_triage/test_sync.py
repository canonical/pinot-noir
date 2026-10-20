from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import startriage.sources.launchpad.triage as lp_triage
from django.test import SimpleTestCase
from startriage.ai import AgentResult, BugOutcome
from startriage.ai.phases import PhaseOutcome, PhaseState
from startriage.config import TeamConfig
from startriage.dates import triage_task_date_range
from startriage.output import Flag, Link, ReportItem
from startriage.source import TaskFilterOptions

from .sync import (
    bug_details,
    build_config,
    context_label,
    item_data,
    markdown_filename,
    report_heading,
    triage_items,
)
from .tasks import _default_triage_day, _launchpad_credentials


def _item(source: str, key: str, **kwargs) -> ReportItem:
    return ReportItem(
        source=source, key=key, label=key, url=f"https://x/{key}", title="t", **kwargs
    )


def _opts(start: datetime, end: datetime) -> TaskFilterOptions:
    return TaskFilterOptions(
        team="server",
        start=start,
        end=end,
        recent_since=start,
        old_since=start,
        sources=frozenset(),
    )


class TriageItemsTests(SimpleTestCase):
    def test_sections_follow_html_report_order(self):
        rows = triage_items(
            [_item("discourse", "d1"), _item("github", "g1"), _item("launchpad", "LP: #1")]
        )
        self.assertEqual(
            [(r.section, r.key) for r in rows],
            [("Launchpad", "LP: #1"), ("GitHub", "g1"), ("Discourse", "d1")],
        )
        self.assertEqual([r.section_order for r in rows], [0, 1, 2])

    def test_item_fields(self):
        item = _item(
            "launchpad",
            "1",
            context=[Link("mysql-8.0", "https://lp/mysql")],
            assignees=[Link("lvoytek", "https://lp/~lvoytek")],
            releases=[("J", "open"), ("D", "closed")],
            further=["noble: New"],
            flags={Flag.NEW, Flag.EXPIRING, Flag.OLD},
        )
        row = item_data(item, "Launchpad", 0, 3)
        self.assertEqual(row.context, [["mysql-8.0", "https://lp/mysql"]])
        self.assertEqual(row.releases, [["J", "open"], ["D", "closed"]])
        self.assertEqual(row.chips, ["new", "expiring"])
        self.assertEqual(row.position, 3)

    def test_gone_items_have_no_chips(self):
        row = item_data(_item("launchpad", "1", flags={Flag.GONE, Flag.NEW}), "Launchpad", 0, 0)
        self.assertEqual(row.chips, [])

    def test_context_label(self):
        self.assertEqual(context_label(["launchpad", "launchpad"]), "Package")
        self.assertEqual(context_label(["launchpad", "github"]), "Package / Repo")


class HeadingTests(SimpleTestCase):
    def test_monday_triage(self):
        start, end = triage_task_date_range("monday", today=date(2026, 10, 19))
        title, subtitle = report_heading(_opts(start, end))
        self.assertEqual(title, "Triage 2026-10-{16,17,18}")
        self.assertEqual(
            subtitle,
            "team server, items updated between 2026-10-16 (Friday) and "
            "2026-10-18 (Sunday) inclusive",
        )

    def test_single_day(self):
        start, end = triage_task_date_range("tuesday", today=date(2026, 10, 20))
        title, subtitle = report_heading(_opts(start, end))
        self.assertEqual(title, "Triage 2026-10-19")
        self.assertEqual(subtitle, "team server, items updated on 2026-10-19 (Monday)")

    def test_explicit_times(self):
        start = datetime(2026, 10, 19, 6, tzinfo=UTC)
        title, subtitle = report_heading(_opts(start, start + timedelta(hours=1)))
        self.assertEqual(title, "Triage 2026-10-19T06:00:00+00:00->2026-10-19T07:00:00+00:00")
        self.assertEqual(
            subtitle,
            "team server, items updated from 2026-10-19T06:00:00+00:00 until "
            "2026-10-19T07:00:00+00:00",
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


class BugDetailsTests(SimpleTestCase):
    def test_combines_descriptions_and_outcomes(self):
        result = AgentResult.model_validate(
            {"bug": "1", "status": "Triaged", "proposed_fix": {"kind": "none"}}
        )
        phase = PhaseOutcome(
            phase="triage",
            state=PhaseState.done,
            summary="checked\n the  changelog",
            tool_calls=["pkg_changelog", "lp_get_bug", "pkg_changelog"],
            input_tokens=1200,
            output_tokens=300,
            sessions=1,
            feedback="mention SRU",
        )
        details = bug_details(
            {"1": "d1", "2": "d2", "3": "d3", "4": "d4"},
            [
                BugOutcome(bug="1", result=result, route="triage", phases=[phase]),
                BugOutcome(bug="2", error="bad json"),
                BugOutcome(bug="4", route="skip-recent", note="Team replied recently."),
            ],
        )
        self.assertEqual(details["1"].description, "d1")
        self.assertEqual((details["1"].ai_result or {}).get("status"), "Triaged")
        self.assertEqual(details["1"].ai_route, "triage")
        self.assertEqual(
            details["1"].ai_phases,
            [
                {
                    "phase": "triage",
                    "state": "done",
                    "summary": "checked the changelog",
                    "tool_calls": ["pkg_changelog", "lp_get_bug", "pkg_changelog"],
                    "tools": "pkg_changelog x2, lp_get_bug",
                    "sessions": 1,
                    "input_tokens": 1200,
                    "output_tokens": 300,
                    "feedback": "mention SRU",
                }
            ],
        )
        self.assertEqual(details["2"].ai_error, "bad json")
        self.assertIsNone(details["3"].ai_result)
        self.assertEqual(details["3"].ai_error, "")
        self.assertIsNone(details["3"].ai_phases)
        self.assertIsNone(details["4"].ai_result)
        self.assertEqual(details["4"].ai_note, "Team replied recently.")


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
