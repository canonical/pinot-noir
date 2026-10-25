import re
from dataclasses import dataclass

from django import forms
from django.core.exceptions import ValidationError
from startriage.ai.tools import REGISTRY, enabled_tool_names
from startriage.config import AIConfig

from pinot_noir.site_admin.forms import LP_NAME

from .models import StartriageAISettings, StartriageTeam

INPUT_CLASS = "p-form-validation__input"


class StartriageAISettingsForm(forms.ModelForm):
    """Edits ``tools`` as a checklist of startriage's agent tools."""

    agent_tools = forms.MultipleChoiceField(
        label="Agent tools",
        required=False,
        widget=forms.CheckboxSelectMultiple,
        choices=[
            (name, f"{name} ({tool.risk}): {tool.summary}") for name, tool in REGISTRY.items()
        ],
        help_text=(
            "As 'startriage config ai-tools'. Tools marked exec run programs on the worker: "
            "fetch_source needs pull-lp-source (ubuntu-dev-tools), patch_applies needs patch. "
            "grep_source and read_source_file need fetch_source. "
            "A phase whose tools are all off is skipped."
        ),
    )

    class Meta:
        model = StartriageAISettings
        exclude = ("tools",)
        labels = {
            "enabled": "Run AI analysis on refreshes",
            "openrouter_base_url": "OpenRouter base URL",
        }
        help_texts = {
            "enabled": "Scheduled and manual refreshes analyse the Launchpad bugs.",
            "model": "Model id, passed to the provider as is.",
            "suggest_improvements": (
                "Ask the model for feedback on startriage's triage skills, shown per bug."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["agent_tools"].initial = enabled_tool_names(
            AIConfig(tools=self.instance.tools)
        )
        for name in ("provider", "model", "openrouter_base_url"):
            self.fields[name].widget.attrs["class"] = INPUT_CLASS

    def save(self, commit=True):
        chosen = set(self.cleaned_data["agent_tools"])
        self.instance.tools = {name: name in chosen for name in REGISTRY}
        return super().save(commit)


def default_team() -> StartriageTeam | None:
    return StartriageTeam.objects.filter(is_default=True).first()


class DefaultTeamForm(forms.ModelForm):
    """The default startriage team's single-value fields; saving makes it the default."""

    class Meta:
        model = StartriageTeam
        fields = ["name", "lp_team", "lp_todo_tag", "lp_freezer_tag", "github_team"]
        labels = {
            "name": "Team name",
            "lp_team": "Launchpad team",
            "lp_todo_tag": "Launchpad to-do tag",
            "lp_freezer_tag": "Launchpad freezer tag",
            "github_team": "GitHub team",
        }
        help_texts = {
            "name": "The startriage team key.",
            "lp_team": "Bugs subscribed to by this team are triaged.",
            "lp_todo_tag": "Tag marking bugs the team needs to work on.",
            "lp_freezer_tag": "Tag marking bugs that are watched but not actionable yet.",
            "github_team": "organization/team-slug whose GitHub activity counts as the team's.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": INPUT_CLASS, "autocomplete": "off"})

    def clean_github_team(self) -> str:
        value = self.cleaned_data["github_team"].strip()
        if value and not re.fullmatch(r"[\w.-]+/[\w.-]+", value):
            raise ValidationError("Enter organization/team-slug.")
        return value

    def save(self, commit=True):
        self.instance.is_default = True
        return super().save(commit)


@dataclass(frozen=True)
class TeamList:
    field: str
    label: str
    singular: str
    help_text: str
    pattern: str = r"\S(.*\S)?"
    error: str = "Enter a value."
    lowercase: bool = False
    # Empty means null: startriage then uses its own default.
    nullable: bool = False


PACKAGE = r"[a-z0-9][a-z0-9+.-]+"
TEAM_LISTS = {
    entry.field: entry
    for entry in (
        TeamList(
            "lp_ignore_packages",
            "Ignored packages",
            "package",
            "Bugs in these source packages are left out.",
            PACKAGE,
            "Enter a source package name.",
            lowercase=True,
        ),
        TeamList(
            "github_repos",
            "GitHub repositories",
            "repository",
            "Repositories whose issues and pull requests are triaged.",
            r"[\w.-]+/[\w.-]+",
            "Enter organization/repository.",
        ),
        TeamList(
            "github_todo_labels",
            "GitHub to-do labels",
            "label",
            "Labels marking issues the team needs to work on. Matches Launchpad "
            "if nothing is entered.",
            nullable=True,
        ),
        TeamList(
            "github_ignore_labels",
            "GitHub ignored labels",
            "label",
            "Issues with any of these labels are left out.",
            nullable=True,
        ),
        TeamList(
            "discourse_categories",
            "Discourse categories",
            "category",
            "Categories to track in triage.",
        ),
        TeamList(
            "discourse_triage_categories",
            "Discourse triage categories",
            "category",
            "Categories containing triage reports.",
        ),
        TeamList(
            "proposed_migration_teams",
            "Proposed migration teams",
            "team",
            "Teams to check proposed migrations for.",
            lowercase=True,
        ),
    )
}


def entry_name(entry) -> str:
    """List entry as shown and matched: github_repos entries may be {"name": ...} objects."""
    return entry.get("name", "") if isinstance(entry, dict) else str(entry)


class TeamEntryForm(forms.Form):
    """Add one entry to a list field of the default team."""

    value = forms.CharField(max_length=200)

    def __init__(self, *args, field: str, team: StartriageTeam, **kwargs):
        self.spec = TEAM_LISTS[field]
        self.team = team
        super().__init__(*args, prefix=f"team-{field}", **kwargs)
        value = self.fields["value"]
        value.label = f"Add {self.spec.singular}"
        value.widget.attrs.update({"class": INPUT_CLASS, "autocomplete": "off"})

    def clean_value(self) -> str:
        value = self.cleaned_data["value"].strip()
        if self.spec.lowercase:
            value = value.lower()
        if self.spec.field == "proposed_migration_teams":
            value = value.lstrip("~")
            LP_NAME(value)
        elif not re.fullmatch(self.spec.pattern, value):
            raise ValidationError(self.spec.error)
        current = getattr(self.team, self.spec.field) or []
        if value in (entry_name(entry) for entry in current):
            raise ValidationError(f"{value} is already added.")
        return value

    def save(self) -> str:
        value = self.cleaned_data["value"]
        field = self.spec.field
        setattr(self.team, field, [*(getattr(self.team, field) or []), value])
        self.team.save(update_fields=[field])
        return value


def remove_team_entry(team: StartriageTeam, field: str, value: str) -> bool:
    current = getattr(team, field) or []
    remaining = [entry for entry in current if entry_name(entry) != value]
    if len(remaining) == len(current):
        return False
    setattr(team, field, remaining or (None if TEAM_LISTS[field].nullable else []))
    team.save(update_fields=[field])
    return True
