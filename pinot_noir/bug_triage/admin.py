from django import forms
from django.contrib import admin
from startriage.ai.tools import REGISTRY, enabled_tool_names
from startriage.config import AIConfig

from .models import StartriageAISettings, StartriageTeam, TriageItem, TriageReport


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["agent_tools"].initial = enabled_tool_names(
            AIConfig(tools=self.instance.tools)
        )

    def save(self, commit=True):
        chosen = set(self.cleaned_data["agent_tools"])
        self.instance.tools = {name: name in chosen for name in REGISTRY}
        return super().save(commit)


@admin.register(StartriageAISettings)
class StartriageAISettingsAdmin(admin.ModelAdmin):
    form = StartriageAISettingsForm
    list_display = ("provider", "model", "enabled", "suggest_improvements")
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "enabled",
                    "provider",
                    "model",
                    "openrouter_base_url",
                    "suggest_improvements",
                    "agent_tools",
                ),
                "description": (
                    "AI analysis of Launchpad bugs, as 'startriage triage --ai'. "
                    "Credentials come from the refreshing user's tokens: github_token for "
                    "Copilot, openrouter_api_key for OpenRouter. Suggest improvements asks "
                    "the model for feedback on startriage's triage skills, shown per bug."
                ),
            },
        ),
    )

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not StartriageAISettings.objects.exists()


@admin.register(StartriageTeam)
class StartriageTeamAdmin(admin.ModelAdmin):
    list_display = ("name", "is_default", "lp_team", "lp_todo_tag", "github_team")
    search_fields = ("name", "lp_team")
    fieldsets = (
        (None, {"fields": ("name", "is_default")}),
        (
            "Launchpad",
            {
                "fields": (
                    "lp_team",
                    "lp_todo_tag",
                    "lp_freezer_tag",
                    "lp_ignore_packages_combined",
                ),
                "description": "Lists are comma-separated.",
            },
        ),
        (
            "Discourse",
            {"fields": ("discourse_categories_combined", "discourse_triage_categories_combined")},
        ),
        (
            "GitHub",
            {
                "fields": (
                    "github_repos",
                    "github_todo_labels_combined",
                    "github_ignore_labels_combined",
                    "github_team",
                ),
                "description": (
                    'github_repos is a JSON list of "org/repo" strings or objects like '
                    '{"name": "org/repo", "todo_labels": ["label"]}. '
                    "Leave the label lists blank to use startriage's defaults."
                ),
            },
        ),
        ("Proposed migration", {"fields": ("proposed_migration_teams_combined",)}),
    )


@admin.register(TriageItem)
class TriageItemAdmin(admin.ModelAdmin):
    list_display = ("label", "section", "status", "importance", "updated", "title", "ai_status")
    list_filter = ("section", "status", "importance")
    search_fields = ("label", "key", "title")

    @admin.display(description="AI status")
    def ai_status(self, obj):
        if obj.ai_result:
            return obj.ai_result.get("status", "")
        if obj.ai_error:
            return "failed"
        return obj.ai_route


@admin.register(TriageReport)
class TriageReportAdmin(admin.ModelAdmin):
    list_display = ("title", "team", "subtitle", "failed_sources", "generated_at")
