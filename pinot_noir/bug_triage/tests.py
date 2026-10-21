import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.test import TestCase
from startriage.ai import BugOutcome
from startriage.config import AIConfig, AIConfigError
from startriage.output import Link, ReportItem
from startriage.sources.launchpad.triage import LaunchpadTriage

from pinot_noir.data_manager.models import UserTokens
from pinot_noir.pages.models import PageMetadata

from .admin import StartriageAISettingsForm
from .apps import PAGE_SLUG
from .models import StartriageAISettings, StartriageTeam, TriageItem, TriageReport
from .sync import BugDetails, build_config
from .tasks import FetchedTriage, _fetch_report_items, _run_ai, refresh_bug_triage


def _team(**kwargs) -> StartriageTeam:
    defaults = {"name": "server", "lp_team": "ubuntu-server", "lp_todo_tag": "server-todo"}
    return StartriageTeam.objects.create(**{**defaults, **kwargs})


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


class BugTriageIndexTests(TestCase):
    def test_empty_page_loads(self):
        response = self.client.get("/bug-triage")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing to do.")

    def test_sections_render(self):
        TriageItem.objects.create(
            source="github",
            key="g1",
            section="GitHub",
            section_order=1,
            label="pollen#1",
            url="https://gh/1",
            title="gh issue",
            context=[["canonical/pollen", "https://gh"]],
        )
        TriageItem.objects.create(
            source="launchpad",
            key="1",
            section="Launchpad",
            section_order=0,
            label="LP: #1",
            url="https://lp/1",
            title="lp bug",
            releases=[["D", "open"]],
            chips=["reply pending"],
        )
        response = self.client.get("/bug-triage")
        sections = response.context["sections"]
        self.assertEqual([s["name"] for s in sections], ["Launchpad", "GitHub"])
        self.assertEqual([s["context_label"] for s in sections], ["Package", "Repo"])
        self.assertContains(response, "reply pending")

    def test_notes_and_markdown_export(self):
        TriageReport.objects.create(
            team="server",
            title="Triage 2026-10-20",
            start=datetime(2026, 10, 20, tzinfo=UTC),
            end=datetime(2026, 10, 21, tzinfo=UTC),
            markdown="# Triage of changes on 2026-10-20\n</script>",
            markdown_filename="triage-2026-10-20.md",
        )
        TriageItem.objects.create(
            source="launchpad", key="7", section="Launchpad", label="LP: #7", url="https://lp/7"
        )
        response = self.client.get("/bug-triage")
        self.assertContains(response, 'id="triage-markdown"')
        # json_script escapes "<", so the template can't end the script element
        self.assertContains(response, "\\u003C/script\\u003E")
        self.assertContains(response, 'data-filename="triage-2026-10-20.md"')
        self.assertContains(response, 'data-report-id="Triage 2026-10-20 ')
        self.assertContains(response, 'data-url="https://lp/7" data-label="LP: #7"')
        self.assertContains(response, 'id="launchpad-7-note" class="js-triage-note"')

    def test_details_dropdown(self):
        TriageItem.objects.create(
            source="launchpad",
            key="7",
            section="Launchpad",
            label="LP: #7",
            url="https://lp/7",
            title="lp bug",
            description="Steps to reproduce",
            ai_result={
                "bug": "7",
                "status": "Triaged",
                "tags": ["regression"],
                "importance": "High",
                "series": {"noble": "Triaged"},
                "duplicate_of": "#123",
                "analysis": "Caused by the new default.",
                "suggested_comment": "Thanks for the report.",
                "proposed_fix": {"kind": "diff", "value": "--- a/x\n+++ b/x"},
                "fix_applies": {"noble": "applies"},
                "references": ["https://example.com/fix"],
                "sru_candidates": [{"series": "noble", "reason": "regression"}],
                "upstream_suggestion": "",
            },
            ai_route="triage",
            ai_phases=[
                {
                    "phase": "triage",
                    "state": "done",
                    "summary": "read the bug",
                    "tools": "lp_get_bug x2",
                    "sessions": 1,
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "feedback": "more examples",
                }
            ],
        )
        TriageItem.objects.create(
            source="launchpad",
            key="8",
            section="Launchpad",
            label="LP: #8",
            url="https://lp/8",
            title="skipped bug",
            ai_route="skip-recent",
            ai_note="Team replied recently.",
        )
        TriageItem.objects.create(
            source="github", key="g", section="GitHub", label="g", url="https://g", title="t"
        )
        response = self.client.get("/bug-triage")
        self.assertContains(response, '<li class="p-list__item" id="launchpad-7" ')
        self.assertContains(response, "<summary>")
        self.assertContains(response, "Steps to reproduce")
        self.assertContains(response, "Caused by the new default.")
        self.assertContains(response, "regression")
        self.assertContains(response, "--- a/x")
        self.assertContains(response, 'href="https://example.com/fix"')
        self.assertContains(response, "<th>Suggested importance</th><td>High</td>")
        self.assertContains(response, "noble: Triaged")
        self.assertContains(response, 'href="https://bugs.launchpad.net/bugs/123">LP: #123</a>')
        self.assertContains(response, "Thanks for the report.")
        self.assertContains(response, "noble: regression")
        self.assertContains(response, "tools: lp_get_bug x2; 10 in / 5 out tokens")
        self.assertContains(response, "more examples")
        self.assertContains(response, "Not triaged by AI: Team replied recently.")
        self.assertContains(response, "No description available.")
        self.assertContains(response, "Not analysed.")


class RefreshBugTriageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="alice")
        self.tokens = UserTokens.objects.create(
            user=self.user, lp_token="lp", github_token="gh", copilot_token="cp"
        )
        _team()

    @patch("pinot_noir.bug_triage.tasks._fetch_report_items", new_callable=AsyncMock)
    def test_replaces_rows(self, fetch_items):
        TriageItem.objects.create(
            source="launchpad",
            key="old",
            section="Launchpad",
            label="old",
            url="https://x",
            title="old",
        )
        fetch_items.return_value = FetchedTriage(
            [
                ReportItem(
                    source="launchpad",
                    key="2",
                    label="LP: #2",
                    url="https://lp/2",
                    title="bug",
                    context=[Link("pkg", "https://lp/pkg")],
                    updated=datetime(2026, 10, 18, tzinfo=UTC),
                )
            ],
            ["discourse"],
            {"2": BugDetails(description="it broke", ai_error="provider error: boom")},
            "# Triage of changes on 2026-10-20\n",
        )

        refresh_bug_triage.call(username="alice", triage_day="tuesday")

        config, opts, ai_provider = fetch_items.call_args.args
        self.assertIsNone(ai_provider)
        item = TriageItem.objects.get()
        self.assertEqual(item.description, "it broke")
        self.assertEqual(item.ai_error, "provider error: boom")
        self.assertEqual(config.general.github_token, "gh")
        self.assertEqual(opts.team, "server")
        self.assertEqual(list(TriageItem.objects.values_list("key", flat=True)), ["2"])
        report = TriageReport.objects.get()
        self.assertEqual(report.failed_sources, ["discourse"])
        self.assertTrue(report.title.startswith("Triage "))
        self.assertEqual(report.markdown, "# Triage of changes on 2026-10-20\n")
        self.assertRegex(report.markdown_filename, r"^triage-\d{4}-\d{2}-\d{2}\.md$")
        self.assertEqual(
            fetch_items.call_args.kwargs["markdown_range"], report.title.removeprefix("Triage")
        )
        self.assertIsNotNone(PageMetadata.objects.get(slug=PAGE_SLUG).last_refreshed_at)

    @patch("pinot_noir.bug_triage.tasks._fetch_report_items", new_callable=AsyncMock)
    def test_all_sources_failed_keeps_rows(self, fetch_items):
        TriageItem.objects.create(
            source="launchpad",
            key="old",
            section="Launchpad",
            label="old",
            url="https://x",
            title="old",
        )
        fetch_items.return_value = FetchedTriage(
            failed=["discourse", "github", "launchpad", "proposed"]
        )
        with self.assertRaises(RuntimeError):
            refresh_bug_triage.call(username="alice", triage_day="tuesday")
        self.assertTrue(TriageItem.objects.filter(key="old").exists())

    @patch("pinot_noir.bug_triage.tasks._fetch_report_items", new_callable=AsyncMock)
    def test_ai_uses_settings_and_user_token(self, fetch_items):
        StartriageAISettings.objects.create(
            enabled=True,
            provider="copilot",
            model="gpt-5",
            tools={"fetch_url": True},
            suggest_improvements=True,
        )
        fetch_items.return_value = FetchedTriage()
        refresh_bug_triage.call(username="alice", triage_day="tuesday")
        config, _opts, ai_provider = fetch_items.call_args.args
        self.assertIsNotNone(ai_provider)
        self.assertEqual(config.ai.model, "gpt-5")
        self.assertEqual(config.ai.github_token, "cp")
        self.assertEqual(config.general.github_token, "gh")
        self.assertEqual(config.ai.tools, {"fetch_url": True})
        self.assertTrue(config.ai.suggest_improvements)

    @patch("pinot_noir.bug_triage.tasks._fetch_report_items", new_callable=AsyncMock)
    def test_ai_disabled_setting_can_be_overridden(self, fetch_items):
        StartriageAISettings.objects.create(enabled=False, provider="copilot", model="gpt-5")
        fetch_items.return_value = FetchedTriage()
        refresh_bug_triage.call(username="alice", triage_day="tuesday")
        self.assertIsNone(fetch_items.call_args.args[2])
        refresh_bug_triage.call(username="alice", triage_day="tuesday", ai=True)
        self.assertIsNotNone(fetch_items.call_args.args[2])

    @patch("pinot_noir.bug_triage.tasks._fetch_report_items", new_callable=AsyncMock)
    def test_ai_without_credentials_fails_before_fetch(self, fetch_items):
        StartriageAISettings.objects.create(enabled=True, provider="openrouter", model="m")
        with self.assertRaises(AIConfigError):
            refresh_bug_triage.call(username="alice", triage_day="tuesday")
        fetch_items.assert_not_called()

    @patch("pinot_noir.bug_triage.tasks.build_provider")
    @patch("pinot_noir.bug_triage.tasks._fetch_report_items", new_callable=AsyncMock)
    def test_copilot_does_not_use_github_token(self, fetch_items, build_provider):
        self.tokens.copilot_token = ""
        self.tokens.save()
        StartriageAISettings.objects.create(enabled=True, provider="copilot", model="gpt-5")
        fetch_items.return_value = FetchedTriage()
        refresh_bug_triage.call(username="alice", triage_day="tuesday")
        config = fetch_items.call_args.args[0]
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
            ai=AIConfig(
                model="m",
                tools={"fetch_url": True, "pkg_versions": False},
                suggest_improvements=True,
            ),
        )
        provider = MagicMock()
        result = self._result()
        outcomes = asyncio.run(_run_ai(config, result, provider))  # type: ignore[arg-type]

        self.assertEqual(outcomes, [BugOutcome(bug="1", error="boom")])
        pipeline, payloads = triage_bugs.call_args.args
        self.assertEqual(payloads, [{"number": "1"}])
        self.assertIs(pipeline.provider, provider)
        self.assertIn("fetch_url", pipeline.tools)
        self.assertNotIn("pkg_versions", pipeline.tools)
        self.assertNotIn("fetch_source", pipeline.tools)
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


@patch("pinot_noir.bug_triage.tasks._launchpad_tasks", return_value=[])
@patch(
    "pinot_noir.bug_triage.tasks.startriage_report._triage_markdown",
    new_callable=AsyncMock,
    return_value="# Triage of changes on 2026-10-19\n\n## Launchpad\n",
)
@patch("pinot_noir.bug_triage.tasks.fetch", new_callable=AsyncMock)
class FetchReportItemsTests(TestCase):
    def _launchpad(self):
        result = MagicMock(spec=LaunchpadTriage)
        result.error = None
        result.report_items = AsyncMock(return_value=[])
        return result

    def test_markdown_is_startriage_report(self, fetch, triage_markdown, _tasks):
        fetch.return_value = {"launchpad": self._launchpad()}
        config = build_config({}, ai=AIConfig(model="m"))
        fetched = asyncio.run(
            _fetch_report_items(config, MagicMock(), markdown_range=" 2026-10-19")
        )
        self.assertEqual(fetched.markdown, "# Triage of changes on 2026-10-19\n\n## Launchpad\n")
        self.assertEqual(triage_markdown.call_args.args[1], " 2026-10-19")

    @patch("pinot_noir.bug_triage.tasks._run_ai", new_callable=AsyncMock)
    def test_ai_report_is_appended(self, run_ai, fetch, _triage_markdown, _tasks):
        fetch.return_value = {"launchpad": self._launchpad()}
        run_ai.return_value = [BugOutcome(bug="5", error="boom")]
        config = build_config({}, ai=AIConfig(model="m"))
        fetched = asyncio.run(_fetch_report_items(config, MagicMock(), MagicMock()))
        human, _, ai = fetched.markdown.partition("\n\n---\n\n")
        self.assertEqual(human, "# Triage of changes on 2026-10-19\n\n## Launchpad\n")
        self.assertIn("AI-generated triage aid", ai)
        self.assertIn("## LP #5 — triage failed", ai)
        self.assertIn("**Error:** boom", ai)


class AISettingsFormTests(TestCase):
    def _data(self, tools):
        return {
            "enabled": "on",
            "provider": "copilot",
            "model": "gpt-5",
            "openrouter_base_url": "https://openrouter.ai/api/v1",
            "agent_tools": tools,
        }

    def test_defaults_are_preselected(self):
        initial = StartriageAISettingsForm().fields["agent_tools"].initial
        self.assertIn("lp_get_bug", initial)
        self.assertNotIn("fetch_url", initial)
        self.assertNotIn("fetch_source", initial)

    def test_saves_every_tool(self):
        form = StartriageAISettingsForm(data=self._data(["lp_get_bug", "fetch_url"]))
        self.assertTrue(form.is_valid(), form.errors)
        settings = form.save()
        self.assertTrue(settings.tools["fetch_url"])
        self.assertTrue(settings.tools["lp_get_bug"])
        self.assertFalse(settings.tools["pkg_versions"])
        initial = StartriageAISettingsForm(instance=settings).fields["agent_tools"].initial
        self.assertEqual(initial, ["lp_get_bug", "fetch_url"])
