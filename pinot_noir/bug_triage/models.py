from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import TruncDate
from django.utils import timezone
from pydantic import ValidationError as PydanticValidationError
from startriage.ai.tools import REGISTRY
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
    UserTokens: copilot_token for Copilot, openrouter_api_key for OpenRouter.
    Their github_token is only used for GitHub data (config general.github_token).
    Every registered agent tool is enabled; tool selection is not configurable.
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
    # Ask the model what to improve in startriage's triage skills.
    suggest_improvements = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Startriage AI Settings"
        verbose_name_plural = "Startriage AI Settings"

    def __str__(self) -> str:
        return f"{self.provider}: {self.model}"

    def to_ai_config(self, copilot_token: str = "", openrouter_api_key: str = "") -> AIConfig:
        """Return the startriage AIConfig, with the given user's credentials."""
        return AIConfig(
            provider=AIProvider(self.provider),
            model=self.model,
            github_token=copilot_token or None,
            openrouter_api_key=openrouter_api_key or None,
            openrouter_base_url=self.openrouter_base_url,
            tools={name: True for name in REGISTRY},
            suggest_improvements=self.suggest_improvements,
        )


class TriageSettings(models.Model):
    """Bug Triage report retention; only one row is used."""

    retention_days = models.PositiveIntegerField(
        default=7,
        validators=[MinValueValidator(1)],
        help_text=(
            "Number of daily reports to keep. Older reports are hidden and removed on refresh."
        ),
    )

    class Meta:
        verbose_name = "Bug Triage Settings"
        verbose_name_plural = "Bug Triage Settings"

    @classmethod
    def current(cls) -> "TriageSettings":
        return cls.objects.first() or cls()

    def available_reports(self):
        """Reports within the age limit, newest first."""
        cutoff = timezone.now() - timedelta(days=self.retention_days)
        return (
            TriageReport.objects.exclude(html="")
            .filter(generated_at__gte=cutoff)
            .order_by("-generated_at", "-pk")
        )

    def report_history(self):
        """At most retention_days daily reports, newest first."""
        return self.available_reports()[: self.retention_days]

    def prune_reports(self) -> None:
        """Enforce the daily-report retention limit immediately."""
        keep = list(self.report_history().values_list("pk", flat=True))
        TriageReport.objects.exclude(pk__in=keep).delete()


class TriageReport(models.Model):
    """One self-contained HTML and Markdown report from startriage triage."""

    team = models.CharField(max_length=100)
    start = models.DateTimeField()
    end = models.DateTimeField()

    # Names of the sources whose fetch failed.
    failed_sources = models.JSONField(default=list, blank=True)

    # startriage's own interactive HTML report and its full Markdown report,
    # including the AI appendix when AI analysis was requested.
    html = models.TextField(blank=True, default="")
    markdown = models.TextField(blank=True)
    markdown_filename = models.CharField(max_length=100, blank=True)

    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(TruncDate("start"), name="unique_triage_report_date"),
        ]

    @property
    def html_filename(self) -> str:
        if not self.markdown_filename:
            return "triage.html"
        return self.markdown_filename.removesuffix(".md") + ".html"

    def __str__(self) -> str:
        return f"Bug Triage ({self.team}, {self.generated_at:%Y-%m-%d})"
