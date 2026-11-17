from pathlib import Path

from django.conf import settings
from django.db import models


class HousekeepingSettings(models.Model):
    """The Git repository in which startriage stores its saved-bug lists."""

    repository = models.CharField(
        max_length=500,
        help_text="Git URL or local path to clone. Use an SSH URL to push with an SSH key.",
    )
    working_directory = models.CharField(
        max_length=500,
        default="data/bug-housekeeping",
        help_text=(
            "Persistent local checkout. A relative path is resolved from the "
            "application directory."
        ),
    )

    class Meta:
        verbose_name = "Bug Housekeeping Settings"
        verbose_name_plural = "Bug Housekeeping Settings"

    def __str__(self) -> str:
        return self.repository

    def checkout_path(self) -> Path:
        path = Path(self.working_directory).expanduser()
        return path if path.is_absolute() else Path(settings.BASE_DIR) / path


class HousekeepingReport(models.Model):
    """The latest self-contained HTML report produced by startriage todo."""

    team = models.CharField(max_length=100)
    html = models.TextField()
    filename = models.CharField(max_length=100)
    saved_bugs_file = models.CharField(max_length=100)
    failed_sources = models.JSONField(default=list, blank=True)

    # Empty when this refresh did not need a new commit. pushed means Git
    # successfully sent all local commits, including earlier ones, to origin.
    commit_hash = models.CharField(max_length=40, blank=True)
    pushed = models.BooleanField(default=False)
    # A report remains useful when its saved-bug list could not be committed or pushed.
    git_error = models.TextField(blank=True)

    generated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Bug Housekeeping ({self.team}, {self.generated_at:%Y-%m-%d})"
