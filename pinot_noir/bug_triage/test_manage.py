from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django_tasks_db.models import DBTaskResult
from startriage.ai.tools import REGISTRY

from pinot_noir.data_manager.models import UserTokens

from .models import StartriageAISettings, StartriageTeam
from .tasks import refresh_bug_triage

LP_CREDS = "[1]\nconsumer_key = x\n"


class BugTriageManageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", is_staff=True)
        self.client.force_login(self.user)
        self.url = reverse("site_admin:bug_triage:index")

    def post(self, **data):
        return self.client.post(self.url, data, follow=True)

    def save_team(self, **overrides):
        data = {
            "action": "team-settings",
            "team-name": "server",
            "team-lp_team": "ubuntu-server",
            "team-lp_todo_tag": "server-todo",
            "team-lp_freezer_tag": "",
            "team-github_team": "",
        }
        data.update(overrides)
        return self.post(**data)

    def add(self, field, value):
        return self.post(action="team-add", field=field, **{f"team-{field}-value": value})

    def remove(self, field, value):
        return self.post(action="team-remove", field=field, value=value)

    def team(self):
        return StartriageTeam.objects.get(is_default=True)

    # Page

    def test_mounted_under_manage_with_page_slug(self):
        self.assertEqual(self.url, "/manage/bug-triage/")

    def test_staff_only(self):
        self.client.force_login(User.objects.create_user("bob"))
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_renders_sections(self):
        response = self.client.get(self.url)
        for heading in ("Settings", "Default team", "AI analysis", "Schedule", "Commands"):
            self.assertContains(response, heading)
        self.assertContains(response, "Create team")
        self.assertNotContains(response, "Ignored packages")  # lists need a saved team

    # Default team

    def test_create_default_team(self):
        response = self.save_team()
        self.assertContains(response, "Saved the default team.")
        team = self.team()
        self.assertEqual(
            (team.name, team.lp_team, team.lp_todo_tag), ("server", "ubuntu-server", "server-todo")
        )
        self.assertContains(response, "Ignored packages")

    def test_edits_existing_default_not_other_teams(self):
        StartriageTeam.objects.create(name="other", lp_team="x", lp_todo_tag="y")
        StartriageTeam.objects.create(
            name="server", lp_team="old", lp_todo_tag="t", is_default=True
        )
        response = self.save_team(**{"team-lp_freezer_tag": "server-freezer"})
        self.assertContains(response, "1 other team can be edited in the Django admin.")
        self.assertEqual(StartriageTeam.objects.count(), 2)
        team = self.team()
        self.assertEqual((team.lp_team, team.lp_freezer_tag), ("ubuntu-server", "server-freezer"))
        self.assertEqual(StartriageTeam.objects.get(name="other").lp_team, "x")

    def test_team_validation(self):
        response = self.save_team(**{"team-lp_team": "", "team-github_team": "no-slash"})
        self.assertContains(response, "This field is required.")
        self.assertContains(response, "Enter organization/team-slug.")
        self.assertFalse(StartriageTeam.objects.exists())

    def test_list_entries_one_at_a_time(self):
        self.save_team()
        self.assertContains(self.add("lp_ignore_packages", " Linux "), "Added linux.")
        self.add("lp_ignore_packages", "glibc")
        self.add("github_repos", "canonical/ubuntu-server-documentation")
        self.add("github_todo_labels", "help wanted")
        self.add("proposed_migration_teams", "~Ubuntu-Server")
        team = self.team()
        self.assertEqual(team.lp_ignore_packages, ["linux", "glibc"])
        self.assertEqual(team.github_repos, ["canonical/ubuntu-server-documentation"])
        self.assertEqual(team.github_todo_labels, ["help wanted"])
        self.assertEqual(team.proposed_migration_teams, ["ubuntu-server"])
        team.to_team_config()  # still a valid startriage team
        response = self.client.get(self.url)
        self.assertContains(response, '<span class="p-chip__value">glibc</span>', html=True)

    def test_list_entry_validation(self):
        self.save_team()
        self.add("lp_ignore_packages", "linux")
        self.assertContains(self.add("lp_ignore_packages", "LINUX"), "linux is already added.")
        self.assertContains(
            self.add("lp_ignore_packages", "two words"), "Enter a source package name."
        )
        self.assertContains(self.add("github_repos", "no-slash"), "Enter organization/repository.")
        self.assertContains(
            self.add("proposed_migration_teams", "a b"), "Enter a Launchpad user name."
        )
        self.assertEqual(self.team().lp_ignore_packages, ["linux"])

    def test_remove_entry_and_null_lists(self):
        self.save_team()
        self.add("github_ignore_labels", "wontfix")
        self.add("discourse_categories", "project/server")
        self.assertContains(self.remove("github_ignore_labels", "wontfix"), "Removed wontfix.")
        self.remove("discourse_categories", "project/server")
        team = self.team()
        self.assertIsNone(team.github_ignore_labels)  # back to startriage's default
        self.assertEqual(team.discourse_categories, [])
        self.assertContains(
            self.remove("discourse_categories", "nope"), "nope isn&#x27;t in the list."
        )

    def test_repo_objects_shown_and_removed_by_name(self):
        repo = {"name": "org/repo", "todo_labels": ["triage"]}
        StartriageTeam.objects.create(
            name="server",
            lp_team="t",
            lp_todo_tag="x",
            is_default=True,
            github_repos=[repo, "org/b"],
        )
        response = self.client.get(self.url)
        self.assertContains(response, "Has its own label settings")
        self.assertContains(self.add("github_repos", "org/repo"), "org/repo is already added.")
        self.remove("github_repos", "org/repo")
        self.assertEqual(self.team().github_repos, ["org/b"])

    def test_list_posts_need_a_team(self):
        response = self.add("lp_ignore_packages", "linux")
        self.assertContains(response, "Save the default team first.")
        self.save_team()
        self.assertContains(self.add("is_default", "x"), "Save the default team first.")

    # AI settings

    def ai_data(self, **overrides):
        data = {
            "action": "ai-settings",
            "ai-enabled": "on",
            "ai-provider": "copilot",
            "ai-model": "some-model",
            "ai-openrouter_base_url": "https://openrouter.ai/api/v1",
            "ai-agent_tools": ["lp_get_bug", "fetch_url"],
        }
        data.update(overrides)
        return data

    def test_save_ai_settings(self):
        response = self.post(**self.ai_data())
        self.assertContains(response, "Saved the AI settings.")
        settings = StartriageAISettings.objects.get()
        self.assertTrue(settings.enabled)
        self.assertFalse(settings.suggest_improvements)
        self.assertEqual((settings.provider, settings.model), ("copilot", "some-model"))
        self.assertEqual(
            {name for name, on in (settings.tools or {}).items() if on},
            {"lp_get_bug", "fetch_url"},
        )
        self.assertEqual(set(settings.tools or {}), set(REGISTRY))
        # Saving again edits the same row.
        self.post(**self.ai_data(**{"ai-model": "other"}))
        self.assertEqual(StartriageAISettings.objects.get().model, "other")

    def test_ai_settings_validation(self):
        response = self.post(**self.ai_data(**{"ai-provider": "nope", "ai-model": ""}))
        self.assertContains(response, "Select a valid choice.")
        self.assertFalse(StartriageAISettings.objects.exists())

    # Schedule and commands

    def test_refresh_is_the_only_task(self):
        response = self.client.get(self.url)
        self.assertEqual([c.name for c in response.context["commands"]], [refresh_bug_triage.name])
        choices = [v for v, _ in response.context["schedule_form"].fields["task"].choices]
        self.assertEqual([c for c in choices if c], [refresh_bug_triage.name])

    def test_run_refresh_uses_default_team(self):
        UserTokens.objects.create(user=self.user, lp_token=LP_CREDS)
        response = self.post(action="run", task=refresh_bug_triage.name)
        self.assertContains(response, "Queued: Refresh bug triage.")
        result = DBTaskResult.objects.get(task_path=refresh_bug_triage.module_path)
        # No team kwarg: the task uses the default team.
        self.assertEqual(result.args_kwargs["kwargs"], {"username": "alice"})
