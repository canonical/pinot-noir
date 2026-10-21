from django.core.exceptions import ValidationError
from django.db import models
from pydantic import ValidationError as PydanticValidationError
from startriage.config import AIConfig, AIProvider, TeamConfig


class StartriageTeam(models.Model):
    """A startriage ``[team.<name>]`` config section.

    Field names follow startriage's TeamConfig; list values are JSON lists.
    """

    # Team key, as passed to ``startriage -t <name>``.
    name = models.SlugField(max_length=100, unique=True)

    # Use this team when the refresh task is not given one (general.default_team).
    is_default = models.BooleanField(default=False)

    lp_team = models.CharField(max_length=100)
    lp_todo_tag = models.CharField(max_length=100)
    lp_freezer_tag = models.CharField(max_length=100, blank=True)
    lp_ignore_packages = models.JSONField(default=list, blank=True)

    discourse_categories = models.JSONField(default=list, blank=True)
    discourse_triage_categories = models.JSONField(default=list, blank=True)

    # Null means unset, so startriage falls back to lp_todo_tag / no ignore labels.
    github_todo_labels = models.JSONField(null=True, blank=True)
    github_ignore_labels = models.JSONField(null=True, blank=True)

    # List of "org/repo" strings or {"name": ..., "todo_labels": [...], ...} objects.
    github_repos = models.JSONField(default=list, blank=True)

    # org/team-slug whose GitHub activity counts as the team's own.
    github_team = models.CharField(max_length=200, blank=True)

    proposed_migration_teams = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = "Startriage Team"
        verbose_name_plural = "Startriage Teams"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True),
                name="single_default_startriage_team",
            )
        ]

    def __str__(self) -> str:
        return self.name

    def to_team_config(self) -> TeamConfig:
        """Return the startriage TeamConfig for this team."""
        return TeamConfig(
            lp_team=self.lp_team,
            lp_todo_tag=self.lp_todo_tag,
            lp_freezer_tag=self.lp_freezer_tag or None,
            lp_ignore_packages=self.lp_ignore_packages or [],
            discourse_categories=self.discourse_categories or [],
            discourse_triage_categories=self.discourse_triage_categories or [],
            github_todo_labels=self.github_todo_labels,
            github_ignore_labels=self.github_ignore_labels,
            github_repos=self.github_repos or [],
            github_team=self.github_team or None,
            proposed_migration_teams=self.proposed_migration_teams or [],
        )

    def clean(self) -> None:
        try:
            self.to_team_config()
        except (PydanticValidationError, ValueError) as exc:
            raise ValidationError(f"Invalid startriage team config: {exc}") from exc


class StartriageAISettings(models.Model):
    """startriage ``[ai]`` settings for ``triage --ai`` runs of the bug triage page.

    Only one row is used. Credentials come from the refreshing user's
    UserTokens: github_token for Copilot, openrouter_api_key for OpenRouter.
    """

    PROVIDER_COPILOT = AIProvider.copilot.value
    PROVIDER_OPENROUTER = AIProvider.openrouter.value
    PROVIDER_CHOICES = [
        (PROVIDER_COPILOT, "GitHub Copilot"),
        (PROVIDER_OPENROUTER, "OpenRouter"),
    ]

    # Run the AI analysis on scheduled refreshes.
    enabled = models.BooleanField(default=False)

    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    # Model id passed to the provider as is.
    model = models.CharField(max_length=200)
    openrouter_base_url = models.URLField(default="https://openrouter.ai/api/v1")
    # startriage ``[ai.tools]``: {tool name: enabled}; null uses each tool's default.
    tools = models.JSONField(null=True, blank=True)
    # Ask the model what to improve in startriage's triage skills.
    suggest_improvements = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Startriage AI Settings"
        verbose_name_plural = "Startriage AI Settings"

    def __str__(self) -> str:
        return f"{self.provider}: {self.model}"

    def to_ai_config(self, github_token: str = "", openrouter_api_key: str = "") -> AIConfig:
        """Return the startriage AIConfig, with the given user's credentials."""
        return AIConfig(
            provider=AIProvider(self.provider),
            model=self.model,
            github_token=github_token or None,
            openrouter_api_key=openrouter_api_key or None,
            openrouter_base_url=self.openrouter_base_url,
            tools=self.tools,
            suggest_improvements=self.suggest_improvements,
        )


class TriageReport(models.Model):
    """Header of the latest triage run; only one row is kept."""

    team = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=300, blank=True)
    start = models.DateTimeField()
    end = models.DateTimeField()

    # Names of the sources whose fetch failed.
    failed_sources = models.JSONField(default=list, blank=True)

    # startriage's markdown report (``triage --markdown FILE [--ai]``), which
    # the page exports with the user's notes, and its download file name.
    markdown = models.TextField(blank=True)
    markdown_filename = models.CharField(max_length=100, blank=True)

    generated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.title} ({self.team})"


class TriageItem(models.Model):
    """One row of the triage report, as produced by startriage's ReportItem."""

    source = models.CharField(max_length=50)
    key = models.CharField(max_length=200)

    # Section heading ("Launchpad", "GitHub", ...) and display order.
    section = models.CharField(max_length=100)
    section_order = models.IntegerField(default=0)
    position = models.IntegerField(default=0)

    label = models.CharField(max_length=200)
    url = models.URLField(max_length=500)
    title = models.TextField()

    # Lists of [text, url] pairs; url may be empty for plain text.
    context = models.JSONField(default=list, blank=True)
    refs = models.JSONField(default=list, blank=True)
    assignees = models.JSONField(default=list, blank=True)

    status = models.CharField(max_length=100, blank=True)
    importance = models.CharField(max_length=100, blank=True)
    updated = models.DateTimeField(null=True, blank=True)

    # List of [series letter, state] pairs; state is open, closed or unapproved.
    releases = models.JSONField(default=list, blank=True)

    # Other tasks of the same bug.
    further = models.JSONField(default=list, blank=True)

    # Chip labels shown next to the title ("new", "reply pending", ...).
    chips = models.JSONField(default=list, blank=True)

    # Bug description (Launchpad only).
    description = models.TextField(blank=True)

    # startriage AgentResult (``--ai``) as JSON, or the reason the analysis failed.
    ai_result = models.JSONField(null=True, blank=True)
    ai_error = models.TextField(blank=True)
    # startriage precheck route, why the bug was not sent to the model, and
    # what each pipeline phase did (sync.phase_data).
    ai_route = models.CharField(max_length=50, blank=True)
    ai_note = models.TextField(blank=True)
    ai_phases = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["section_order", "position"]
        constraints = [
            models.UniqueConstraint(fields=["source", "key"], name="unique_triage_item_per_source")
        ]

    def __str__(self) -> str:
        return f"{self.label} - {self.title}"
