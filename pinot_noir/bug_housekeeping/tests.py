import shlex
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase
from django.urls import reverse

from pinot_noir.bug_triage.models import StartriageTeam
from pinot_noir.data_manager.models import UserTokens
from pinot_noir.pages.models import PageMetadata

from .apps import PAGE_SLUG
from .models import HousekeepingReport, HousekeepingSettings
from .tasks import _git_environment, refresh_bug_housekeeping

HTML = "<!doctype html><title>Bug housekeeping</title><p>startriage report</p>"


def git(
    *args: str, cwd: Path | None = None, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=check)


class BugHousekeepingViewTests(TestCase):
    def test_empty_page_loads(self):
        response = self.client.get(reverse("bug_housekeeping:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Nothing to do.")
        self.assertNotContains(response, "<iframe")

    def test_report_is_embedded_and_downloadable(self):
        HousekeepingReport.objects.create(
            team="server",
            html=HTML,
            filename="todo-2026-11-17.html",
            saved_bugs_file="todo-2026-11-17.yaml",
            commit_hash="a" * 40,
        )
        response = self.client.get(reverse("bug_housekeeping:index"))
        self.assertContains(response, "Open HTML")
        self.assertContains(response, "Save HTML")
        self.assertContains(response, 'src="/bug-housekeeping/report.html"')
        self.assertContains(response, "background: #fff; color-scheme: light;")
        self.assertNotContains(response, "kept in the local checkout")
        self.assertNotContains(response, "todo-2026-11-17.yaml")
        self.assertNotContains(response, "a" * 40)

        raw = self.client.get(reverse("bug_housekeeping:report"))
        self.assertEqual(raw.content.decode(), HTML)
        self.assertEqual(raw["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("frame-ancestors 'self'", raw["Content-Security-Policy"])

        download = self.client.get(reverse("bug_housekeeping:download"))
        self.assertEqual(download.content.decode(), HTML)
        self.assertEqual(
            download["Content-Disposition"], 'attachment; filename="todo-2026-11-17.html"'
        )

    def test_git_status_is_staff_only(self):
        HousekeepingReport.objects.create(
            team="server",
            html=HTML,
            filename="todo-2026-11-17.html",
            saved_bugs_file="todo-2026-11-17.yaml",
            commit_hash="b" * 40,
        )
        self.client.force_login(User.objects.create_user("nonstaff"))
        response = self.client.get(reverse("bug_housekeeping:index"))
        self.assertNotContains(response, "Saved bugs:")
        self.assertNotContains(response, "todo-2026-11-17.yaml")
        self.assertNotContains(response, "b" * 40)
        self.assertNotContains(response, "local checkout")
        self.assertContains(response, "Team server.")

        self.client.force_login(User.objects.create_user("staff", is_staff=True))
        response = self.client.get(reverse("bug_housekeeping:index"))
        self.assertContains(response, "Saved bugs:")
        self.assertContains(response, "todo-2026-11-17.yaml")
        self.assertContains(response, "b" * 40)
        self.assertContains(response, "kept in the local checkout")

    def test_missing_report_is_404(self):
        self.assertEqual(self.client.get(reverse("bug_housekeeping:report")).status_code, 404)
        self.assertEqual(self.client.get(reverse("bug_housekeeping:download")).status_code, 404)


class GitEnvironmentTests(TestCase):
    def test_private_key_is_a_temporary_ssh_identity(self):
        with _git_environment("private key") as env:
            self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
            command = shlex.split(env["GIT_SSH_COMMAND"])
            key_path = Path(command[command.index("-i") + 1])
            self.assertEqual(key_path.read_text(), "private key\n")
            self.assertEqual(key_path.stat().st_mode & 0o777, 0o600)
            self.assertIn("IdentitiesOnly=yes", command)
        self.assertFalse(key_path.exists())

    def test_no_key_disables_prompts_without_an_ssh_identity(self):
        with _git_environment("") as env:
            self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
            self.assertNotIn("GIT_SSH_COMMAND", env)


class RefreshBugHousekeepingTests(TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.origin = self.root / "saved-bugs.git"
        self.workdir = self.root / "checkout"
        git("init", "--bare", "--initial-branch=main", str(self.origin))

        self.user = User.objects.create_user(
            "alice", email="alice@example.com", first_name="Alice Example"
        )
        self.tokens = UserTokens.objects.create(user=self.user, lp_token="lp", github_token="gh")
        HousekeepingSettings.objects.create(
            repository=str(self.origin), working_directory=str(self.workdir)
        )
        StartriageTeam.objects.create(
            name="server",
            lp_team="ubuntu-server",
            lp_todo_tag="server-todo",
            is_default=True,
        )

    @staticmethod
    async def generate(config, opts, output):
        output.html_path.write_text(HTML, encoding="utf-8")
        output.bug_persistor.record("launchpad", {"123"})
        output.bug_persistor.save()
        return {"launchpad": SimpleNamespace(error=None)}

    @patch("pinot_noir.bug_housekeeping.tasks.startriage_todo", new_callable=AsyncMock)
    def test_commits_locally_then_pushes_when_a_key_is_available(self, todo):
        todo.side_effect = self.generate

        global_config = self.root / "gitconfig"
        global_config.write_text("[commit]\n\tgpgsign = true\n", encoding="utf-8")
        with patch.dict("os.environ", {"GIT_CONFIG_GLOBAL": str(global_config)}):
            refresh_bug_housekeeping.call(username="alice")

        todo.assert_awaited_once()
        config, opts, output = todo.await_args.args
        self.assertEqual(config.general.github_token, "gh")
        self.assertEqual(opts.team, "server")
        self.assertEqual({source.name for source in opts.sources}, {"launchpad", "github"})
        recent_seconds = (datetime.now(UTC) - opts.recent_since).total_seconds()
        self.assertAlmostEqual(recent_seconds, 6 * 24 * 60 * 60, delta=5)
        self.assertEqual(output.bug_persistor._save_path.parent, self.workdir / "savebugs")

        report = HousekeepingReport.objects.get()
        self.assertTrue((self.workdir / report.saved_bugs_file).is_file())
        self.assertFalse((self.workdir / Path(report.saved_bugs_file).name).exists())
        self.assertEqual(report.html, HTML)
        self.assertFalse(report.pushed)
        self.assertTrue(report.commit_hash)
        self.assertEqual(
            git("rev-parse", "HEAD", cwd=self.workdir).stdout.strip(), report.commit_hash
        )
        self.assertEqual(
            git("log", "-1", "--format=%an|%ae", cwd=self.workdir).stdout.strip(),
            "Alice Example|alice@example.com",
        )
        self.assertEqual(git("status", "--porcelain", cwd=self.workdir).stdout, "")
        self.assertEqual(
            git("config", "--local", "--get", "commit.gpgsign", cwd=self.workdir).stdout.strip(),
            "false",
        )
        bare_head = git("--git-dir", str(self.origin), "rev-parse", "HEAD", check=False)
        self.assertNotEqual(bare_head.returncode, 0)
        self.assertIsNotNone(PageMetadata.objects.get(slug=PAGE_SLUG).last_refreshed_at)

        # The second report has the same bug list, so it needs no new commit.
        # Adding a key nevertheless publishes the earlier local-only commit.
        self.tokens.ssh_private_key = "not used by a local transport"
        self.tokens.save()
        refresh_bug_housekeeping.call(username="alice")

        report = HousekeepingReport.objects.get()
        self.assertEqual(HousekeepingReport.objects.count(), 1)
        self.assertEqual(report.commit_hash, "")
        self.assertTrue(report.pushed)
        self.assertEqual(
            git("--git-dir", str(self.origin), "rev-parse", "HEAD").stdout.strip(),
            git("rev-parse", "HEAD", cwd=self.workdir).stdout.strip(),
        )
        self.assertEqual(git("rev-list", "--count", "HEAD", cwd=self.workdir).stdout.strip(), "1")

    @patch("pinot_noir.bug_housekeeping.tasks.startriage_todo", new_callable=AsyncMock)
    @patch("pinot_noir.bug_housekeeping.tasks._commit_and_push")
    def test_git_failure_still_displays_report(self, commit, todo):
        todo.side_effect = self.generate
        commit.side_effect = RuntimeError("commit.gpgsign prevented the commit")

        with self.assertRaisesRegex(RuntimeError, "commit.gpgsign"):
            refresh_bug_housekeeping.call(username="alice")

        report = HousekeepingReport.objects.get()
        self.assertEqual(report.html, HTML)
        self.assertIn("commit.gpgsign prevented the commit", report.git_error)
        self.assertFalse(report.pushed)
        self.assertEqual(report.commit_hash, "")
        self.assertIsNotNone(PageMetadata.objects.get(slug=PAGE_SLUG).last_refreshed_at)

        response = self.client.get(reverse("bug_housekeeping:index"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "saved-bug Git update failed")
        self.assertNotContains(response, "commit.gpgsign prevented the commit")
        self.assertContains(response, 'src="/bug-housekeeping/report.html"')

        staff = User.objects.create_user("admin", is_staff=True)
        self.client.force_login(staff)
        response = self.client.get(reverse("bug_housekeeping:index"))
        self.assertContains(
            response, "The report was generated, but the saved-bug Git update failed"
        )
        self.assertContains(response, "commit.gpgsign prevented the commit")

        raw = self.client.get(reverse("bug_housekeeping:report"))
        self.assertEqual(raw.content.decode(), HTML)

    @patch("pinot_noir.bug_housekeeping.tasks.startriage_todo", new_callable=AsyncMock)
    def test_all_sources_failed_keeps_previous_report(self, todo):
        HousekeepingReport.objects.create(
            team="old", html="old report", filename="old.html", saved_bugs_file="old.yaml"
        )

        async def fail(config, opts, output):
            output.html_path.write_text("failed", encoding="utf-8")
            output.bug_persistor.save()
            return {
                "launchpad": SimpleNamespace(error="down"),
                "github": SimpleNamespace(error="down"),
            }

        todo.side_effect = fail
        with self.assertRaisesRegex(RuntimeError, "All startriage sources failed"):
            refresh_bug_housekeeping.call(username="alice")
        self.assertEqual(HousekeepingReport.objects.get().html, "old report")

    def test_requires_git_settings(self):
        HousekeepingSettings.objects.all().delete()
        with self.assertRaisesRegex(ObjectDoesNotExist, "Configure the saved-bugs Git repository"):
            refresh_bug_housekeeping.call(username="alice")
