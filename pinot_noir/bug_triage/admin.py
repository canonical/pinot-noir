from django.contrib import admin

from .forms import StartriageAISettingsForm, TriageSettingsForm
from .models import StartriageAISettings, StartriageTeam, TriageReport, TriageSettings


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
                ),
                "description": (
                    "AI analysis of Launchpad bugs, as 'startriage triage --ai'. "
                    "Credentials come from the refreshing user's tokens: copilot_token (a "
                    "fine-grained token with Copilot Requests: Read) for Copilot, "
                    "openrouter_api_key for OpenRouter. Suggest improvements asks "
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
                    "lp_ignore_packages",
                ),
            },
        ),
        (
            "Discourse",
            {"fields": ("discourse_categories", "discourse_triage_categories")},
        ),
        (
            "GitHub",
            {
                "fields": (
                    "github_repos",
                    "github_todo_labels",
                    "github_ignore_labels",
                    "github_team",
                ),
                "description": (
                    'github_repos is a list of "org/repo" strings or objects like '
                    '{"name": "org/repo", "todo_labels": ["label"]}. '
                    "Leave the label lists empty (null) to use startriage's defaults."
                ),
            },
        ),
        (
            "Proposed migration",
            {"fields": ("proposed_migration_teams",)},
        ),
    )


@admin.register(TriageSettings)
class TriageSettingsAdmin(admin.ModelAdmin):
    form = TriageSettingsForm
    list_display = ("retention_days",)

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not TriageSettings.objects.exists()


@admin.register(TriageReport)
class TriageReportAdmin(admin.ModelAdmin):
    list_display = ("team", "start", "end", "failed_sources", "generated_at")
