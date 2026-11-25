import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from startriage.ai import BugOutcome
from startriage.ai.tools import REGISTRY
from startriage.config import AIConfig, AIConfigError
from startriage.output import FailedTriageResult, Link, ReportItem
from startriage.source import TaskFilterOptions
from startriage.sources.launchpad.triage import LaunchpadTriage

from pinot_noir.data_manager.models import UserTokens
from pinot_noir.pages.models import PageMetadata

from .apps import PAGE_SLUG
from .models import StartriageAISettings, StartriageTeam, TriageReport, TriageSettings
from .sync import build_config
from .tasks import FetchedTriage, _fetch_report, _run_ai, refresh_bug_triage

HTML = "<!doctype html><title>Triage</title><p>startriage report</p>"


def _team(**kwargs) -> StartriageTeam:
    defaults = {"name": "server", "lp_team": "ubuntu-server", "lp_todo_tag": "server-todo"}
    return StartriageTeam.objects.create(**{**defaults, **kwargs})


def _report(**kwargs) -> TriageReport:
    defaults = {
        "team": "server",
        "start": datetime(2026, 10, 20, tzinfo=UTC),
        "end": datetime(2026, 10, 21, tzinfo=UTC),
        "html": HTML,
        "markdown": "# Triage of changes on 2026-10-20\n",
        "markdown_filename": "triage-2026-10-20.md",
    }
    return TriageReport.objects.create(**{**defaults, **kwargs})


def _age(report: TriageReport, days: int) -> TriageReport:
    TriageReport.objects.filter(pk=report.pk).update(
        generated_at=timezone.now() - timedelta(days=days),
        start=report.start - timedelta(days=days),
        end=report.end - timedelta(days=days),
    )
    report.refresh_from_db()
    return report


def _opts() -> TaskFilterOptions:
    start = datetime(2026, 10, 19, tzinfo=UTC)
    end = datetime(2026, 10, 20, tzinfo=UTC)
    return TaskFilterOptions(
        team="server",
        start=start,
        end=end,
        recent_since=start,
        old_since=start,
        sources=frozenset(),
    )


class StartriageTeamTests(TestCase):
    def test_to_team_config(self):
        team = _team(
            lp_ignore_packages=["lxd", "juju"],
            github_ignore_labels=[],
            github_repos=["canonical/pollen", {"name": "canonical/x", "todo_labels": ["a"]}],
        )
        config = team.to_team_config()
        self.assertEqual(config.lp_ignore_packages, ["lxd", "juju"])
        self.assertIsNone(config.github_todo_labels)
        self.assertEqual(config.github_ignore_labels, [])
        self.assertIsNone(config.lp_freezer_tag)
        self.assertEqual(
            [r.name for r in config.github_repos], ["canonical/pollen", "canonical/x"]
        )
        self.assertEqual(config.github_repos[1].todo_labels, ["a"])

    def test_clean_rejects_non_list(self):
        team = _team(lp_ignore_packages="lxd, juju")
        with self.assertRaises(ValidationError):
            team.clean()

    def test_clean_rejects_bad_repos(self):
        team = _team(github_repos=[{"bogus": 1}])
        with self.assertRaises(ValidationError):
            team.clean()


class TriageReportTests(TestCase):
    def test_only_one_report_per_triage_date(self):
        report = _report()
        with self.assertRaises(IntegrityError), transaction.atomic():
            _report(start=report.start + timedelta(hours=1))


class BugTriageIndexTests(TestCase):
    def test_empty_page_loads(self):
        response = self.client.get(reverse("bug_triage:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing to do.")
        self.assertNotContains(response, "<iframe")

    def test_report_is_embedded_and_downloadable(self):
        _report(failed_sources=["discourse"])
        response = self.client.get(reverse("bug_triage:index"))
        self.assertContains(response, "Open HTML")
        self.assertContains(response, "Save HTML")
        self.assertNotContains(response, "Save full Markdown")
        self.assertContains(response, 'src="/bug-triage/report.html"')
        self.assertContains(response, "background: #fff; color-scheme: light;")
        self.assertContains(response, "Fetching failed: discourse")
        self.assertNotContains(response, "triagenotes.js")

        raw = self.client.get(reverse("bug_triage:report"))
        self.assertEqual(raw.content.decode(), HTML)
        self.assertEqual(raw["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("frame-ancestors 'self'", raw["Content-Security-Policy"])
        self.assertEqual(raw["X-Content-Type-Options"], "nosniff")

        download = self.client.get(reverse("bug_triage:download"))
        self.assertEqual(download.content.decode(), HTML)
        self.assertEqual(
            download["Content-Disposition"], 'attachment; filename="triage-2026-10-20.html"'
        )

    def test_previous_report_selection(self):
        previous = _age(_report(html="previous html"), 1)
        current = _report(html="current html")

        response = self.client.get(reverse("bug_triage:index"))
        self.assertContains(response, f'value="{previous.pk}"')
        self.assertContains(response, f'value="{current.pk}" selected')
        self.assertContains(response, 'src="/bug-triage/report.html"')
        self.assertContains(response, 'onchange="this.form.submit()"')
        self.assertContains(response, 'aria-label="Report"')
        self.assertNotContains(response, '<label for="triage-report">')
        self.assertNotContains(response, "generated")
        self.assertNotContains(response, ">View</button>")

        response = self.client.get(reverse("bug_triage:index"), {"report": previous.pk})
        self.assertContains(response, f'value="{previous.pk}" selected')
        self.assertContains(response, f'src="/bug-triage/report.html?report={previous.pk}"')
        self.assertContains(response, f'href="/bug-triage/download?report={previous.pk}"')
        raw = self.client.get(reverse("bug_triage:report"), {"report": previous.pk})
        self.assertEqual(raw.content.decode(), "previous html")
        download = self.client.get(reverse("bug_triage:download"), {"report": previous.pk})
        self.assertEqual(download.content.decode(), "previous html")

    def test_reports_outside_retention_limit_and_invalid_ids_are_not_available(self):
        TriageSettings.objects.create(retention_days=1)
        previous = _age(_report(html="previous html"), 1)
        _report(html="current html")
        response = self.client.get(reverse("bug_triage:index"))
        self.assertNotContains(response, f'value="{previous.pk}"')
        for url_name in ("index", "report", "download"):
            response = self.client.get(reverse(f"bug_triage:{url_name}"), {"report": previous.pk})
            self.assertEqual(response.status_code, 404)
        self.assertEqual(
            self.client.get(reverse("bug_triage:index"), {"report": "invalid"}).status_code,
            404,
        )

    def test_expired_report_is_not_available(self):
        TriageSettings.objects.create(retention_days=7)
        expired = _age(_report(html="expired html"), 8)
        _report(html="current html")
        response = self.client.get(reverse("bug_triage:index"))
        self.assertNotContains(response, f'value="{expired.pk}"')
        response = self.client.get(reverse("bug_triage:report"), {"report": expired.pk})
        self.assertEqual(response.status_code, 404)

    def test_legacy_report_without_html_needs_a_refresh(self):
        _report(html="")
        response = self.client.get(reverse("bug_triage:index"))
        self.assertContains(response, "Nothing to do.")
        self.assertNotContains(response, "<iframe")
        self.assertEqual(self.client.get(reverse("bug_triage:report")).status_code, 404)
        self.assertEqual(self.client.get(reverse("bug_triage:download")).status_code, 404)

    def test_missing_report_is_404(self):
        self.assertEqual(self.client.get(reverse("bug_triage:report")).status_code, 404)
        self.assertEqual(self.client.get(reverse("bug_triage:download")).status_code, 404)


class RefreshBugTriageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="alice")
        self.tokens = UserTokens.objects.create(
            user=self.user, lp_token="lp", github_token="gh", copilot_token="cp"
        )
        _team()

    @patch("pinot_noir.bug_triage.tasks._fetch_report", new_callable=AsyncMock)
    def test_adds_report_and_keeps_history(self, fetch_report):
        previous = _report(html="old report", markdown="old markdown")
        fetch_report.return_value = FetchedTriage(
            html="new startriage html",
            failed=["discourse"],
            markdown="# Triage of changes on 2026-10-20\n",
        )

        refresh_bug_triage.call(username="alice", triage_day="tuesday")

        config, opts, ai_provider = fetch_report.call_args.args
        self.assertIsNone(ai_provider)
        self.assertEqual(config.general.github_token, "gh")
        self.assertEqual(opts.team, "server")
        report = TriageReport.objects.get(html="new startriage html")
        self.assertEqual(TriageReport.objects.count(), 2)
        self.assertTrue(TriageReport.objects.filter(pk=previous.pk).exists())
        self.assertEqual(report.failed_sources, ["discourse"])
        self.assertEqual(report.markdown, "# Triage of changes on 2026-10-20\n")
        self.assertRegex(report.markdown_filename, r"^triage-\d{4}-\d{2}-\d{2}\.md$")
        self.assertEqual(report.html_filename, report.markdown_filename[:-3] + ".html")
        self.assertIsNotNone(PageMetadata.objects.get(slug=PAGE_SLUG).last_refreshed_at)

    @patch("pinot_noir.bug_triage.tasks._fetch_report", new_callable=AsyncMock)
    def test_same_triage_date_replaces_existing_report(self, fetch_report):
        opts = replace(_opts(), sources=frozenset({"launchpad"}))
        previous = _report(
            start=opts.start + timedelta(hours=5),
            end=opts.end + timedelta(hours=5),
            html="old html",
            markdown="old markdown",
        )
        fetch_report.return_value = FetchedTriage(html="new html", markdown="new markdown")

        with patch("pinot_noir.bug_triage.tasks.build_filter", return_value=opts):
            refresh_bug_triage.call(username="alice")

        self.assertEqual(TriageReport.objects.count(), 1)
        report = TriageReport.objects.get()
        self.assertEqual(report.pk, previous.pk)
        self.assertEqual(report.start, opts.start)
        self.assertEqual(report.html, "new html")
        self.assertEqual(report.markdown, "new markdown")

    @patch("pinot_noir.bug_triage.tasks._fetch_report", new_callable=AsyncMock)
    def test_prunes_history_by_combined_retention_limit(self, fetch_report):
        TriageSettings.objects.create(retention_days=4)
        _age(_report(html="expired"), 8)
        _age(_report(html="count-pruned"), 3)
        _age(_report(html="previous-2"), 2)
        _age(_report(html="previous-1"), 0)
        _age(
            _report(
                html="previous-0",
                start=datetime(2026, 10, 21, tzinfo=UTC),
                end=datetime(2026, 10, 22, tzinfo=UTC),
            ),
            0,
        )
        fetch_report.return_value = FetchedTriage(html="current")

        refresh_bug_triage.call(username="alice", triage_day="tuesday")

        self.assertEqual(
            list(
                TriageReport.objects.order_by("-generated_at", "-pk").values_list(
                    "html", flat=True
                )
            ),
            ["current", "previous-0", "previous-1", "previous-2"],
        )

    @patch("pinot_noir.bug_triage.tasks._fetch_report", new_callable=AsyncMock)
    def test_all_sources_failed_keeps_report(self, fetch_report):
        _report(html="old report")
        fetch_report.return_value = FetchedTriage(
            html="failed", failed=["discourse", "github", "launchpad", "proposed"]
        )
        with self.assertRaises(RuntimeError):
            refresh_bug_triage.call(username="alice", triage_day="tuesday")
        self.assertEqual(TriageReport.objects.get().html, "old report")

    @patch("pinot_noir.bug_triage.tasks._fetch_report", new_callable=AsyncMock)
    def test_ai_uses_settings_and_user_token(self, fetch_report):
        StartriageAISettings.objects.create(
            enabled=True,
            provider="copilot",
            model="gpt-5",
            suggest_improvements=True,
        )
        fetch_report.return_value = FetchedTriage()
        refresh_bug_triage.call(username="alice", triage_day="tuesday")
        config, _opts, ai_provider = fetch_report.call_args.args
        self.assertIsNotNone(ai_provider)
        self.assertEqual(config.ai.model, "gpt-5")
        self.assertEqual(config.ai.github_token, "cp")
        self.assertEqual(config.general.github_token, "gh")
        self.assertEqual(config.ai.tools, {name: True for name in REGISTRY})
        self.assertTrue(config.ai.suggest_improvements)

    @patch("pinot_noir.bug_triage.tasks._fetch_report", new_callable=AsyncMock)
    def test_ai_disabled_setting_can_be_overridden(self, fetch_report):
        StartriageAISettings.objects.create(enabled=False, provider="copilot", model="gpt-5")
        fetch_report.return_value = FetchedTriage()
        refresh_bug_triage.call(username="alice", triage_day="tuesday")
        self.assertIsNone(fetch_report.call_args.args[2])
        refresh_bug_triage.call(username="alice", triage_day="tuesday", ai=True)
        self.assertIsNotNone(fetch_report.call_args.args[2])

    @patch("pinot_noir.bug_triage.tasks._fetch_report", new_callable=AsyncMock)
    def test_ai_without_credentials_fails_before_fetch(self, fetch_report):
        StartriageAISettings.objects.create(enabled=True, provider="openrouter", model="m")
        with self.assertRaises(AIConfigError):
            refresh_bug_triage.call(username="alice", triage_day="tuesday")
        fetch_report.assert_not_called()

    @patch("pinot_noir.bug_triage.tasks.build_provider")
    @patch("pinot_noir.bug_triage.tasks._fetch_report", new_callable=AsyncMock)
    def test_copilot_does_not_use_github_token(self, fetch_report, build_provider):
        self.tokens.copilot_token = ""
        self.tokens.save()
        StartriageAISettings.objects.create(enabled=True, provider="copilot", model="gpt-5")
        fetch_report.return_value = FetchedTriage()
        refresh_bug_triage.call(username="alice", triage_day="tuesday")
        config = fetch_report.call_args.args[0]
        self.assertIsNone(config.ai.github_token)
        self.assertEqual(config.general.github_token, "gh")

    def test_ai_requested_without_settings(self):
        with self.assertRaises(ObjectDoesNotExist):
            refresh_bug_triage.call(username="alice", triage_day="tuesday", ai=True)


class RunAITests(TestCase):
    def _result(self):
        window = (datetime(2026, 10, 19, tzinfo=UTC), datetime(2026, 10, 20, tzinfo=UTC))
        return SimpleNamespace(
            tasks=SimpleNamespace(lp=MagicMock(), tasks=["task"]),
            team_config=SimpleNamespace(lp_team="ubuntu-server"),
            filter=SimpleNamespace(start=window[0], end=window[1]),
        )

    @patch("pinot_noir.bug_triage.tasks.triage_bugs", new_callable=AsyncMock)
    @patch("pinot_noir.bug_triage.tasks.team_members", return_value=frozenset({"ubuntu-server"}))
    @patch("pinot_noir.bug_triage.tasks.payloads_from_tasks", return_value=[{"number": "1"}])
    def test_pipeline_from_config(self, _payloads, _team, triage_bugs):
        triage_bugs.return_value = [BugOutcome(bug="1", error="boom")]
        config = build_config(
            {},
            github_token="gh",
            ai=StartriageAISettings(
                provider="copilot", model="m", suggest_improvements=True
            ).to_ai_config(),
        )
        provider = MagicMock()
        result = self._result()
        outcomes = asyncio.run(_run_ai(config, result, provider))  # type: ignore[arg-type]

        self.assertEqual(outcomes, [BugOutcome(bug="1", error="boom")])
        pipeline, payloads = triage_bugs.call_args.args
        self.assertEqual(payloads, [{"number": "1"}])
        self.assertIs(pipeline.provider, provider)
        self.assertEqual(set(pipeline.tools), set(REGISTRY))
        self.assertEqual(pipeline.team, frozenset({"ubuntu-server"}))
        self.assertEqual(pipeline.window, (result.filter.start, result.filter.end))
        self.assertTrue(pipeline.feedback)
        self.assertIsNone(pipeline.feedback_log)
        self.assertEqual(pipeline.model, "m")

    @patch("pinot_noir.bug_triage.tasks.triage_bugs", new_callable=AsyncMock)
    @patch("pinot_noir.bug_triage.tasks.payloads_from_tasks", return_value=[])
    def test_nothing_to_triage(self, _payloads, triage_bugs):
        config = build_config({}, ai=AIConfig(model="m"))
        self.assertEqual(asyncio.run(_run_ai(config, self._result(), MagicMock())), [])  # type: ignore[arg-type]
        triage_bugs.assert_not_called()


@patch("pinot_noir.bug_triage.tasks.startriage_report.fetch", new_callable=AsyncMock)
class FetchReportTests(TestCase):
    def _launchpad(self):
        result = MagicMock(spec=LaunchpadTriage)
        result.error = None
        result.to_dict = AsyncMock(return_value={})
        result.report_items = AsyncMock(
            return_value=[
                ReportItem(
                    source="launchpad",
                    key="1",
                    label="LP: #1",
                    url="https://lp/1",
                    title="bug",
                    context=[Link("pkg", "https://lp/pkg")],
                )
            ]
        )

        async def print_section(output):
            output.out.write("## Launchpad\n\n#### [LP: #1](https://lp/1) — bug\n")

        result.print_section = AsyncMock(side_effect=print_section)
        return result

    def test_startriage_generates_html_and_markdown(self, fetch):
        fetch.return_value = {"launchpad": self._launchpad()}
        fetched = asyncio.run(_fetch_report(build_config({}), _opts()))
        self.assertIn("<title>Triage 2026-10-19</title>", fetched.html)
        self.assertIn('id="launchpad-1"', fetched.html)
        self.assertIn('var PREFIX = "startriage:"', fetched.html)
        self.assertIn("triage-2026-10-19.md", fetched.html)
        self.assertIn("## Launchpad", fetched.markdown)
        self.assertEqual(fetched.failed, [])

    @patch("pinot_noir.bug_triage.tasks._run_ai", new_callable=AsyncMock)
    def test_ai_report_is_appended_to_markdown(self, run_ai, fetch):
        fetch.return_value = {"launchpad": self._launchpad()}
        run_ai.return_value = [BugOutcome(bug="5", error="boom")]
        fetched = asyncio.run(_fetch_report(build_config({}), _opts(), MagicMock()))
        human, _, ai = fetched.markdown.partition("\n\n---\n\n")
        self.assertIn("## Launchpad", human)
        self.assertIn("AI-generated triage aid", ai)
        self.assertIn("## LP #5 — triage failed", ai)
        self.assertIn("**Error:** boom", ai)
        self.assertNotIn("AI-generated triage aid", fetched.html)

    def test_failed_sources_are_in_startriage_html(self, fetch):
        fetch.return_value = {"launchpad": FailedTriageResult("down")}
        fetched = asyncio.run(_fetch_report(build_config({}), _opts()))
        self.assertEqual(fetched.failed, ["launchpad"])
        self.assertIn("Fetching failed: launchpad", fetched.html)


class AISettingsTests(TestCase):
    def test_all_agent_tools_are_enabled(self):
        settings = StartriageAISettings(provider="copilot", model="gpt-5")
        config = settings.to_ai_config()
        self.assertEqual(config.tools, {name: True for name in REGISTRY})
