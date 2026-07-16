from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.db import models
from django.utils import timezone

from .fields import EncryptedTextField


class UserTokens(models.Model):
    """Tokens for a Django admin user to access external services."""

    class Meta:
        verbose_name = "User Tokens"
        verbose_name_plural = "User Token Groups"

    # The associated Django admin user
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # Launchpad API credentials string
    lp_token = EncryptedTextField()


class MergeBugPackageInfo(models.Model):
    """Information about a package for creating a merges schedule merge bug."""

    # Name of package - primary key
    package = models.CharField(primary_key=True, max_length=200)

    # When creating a new merge board, offset the expected milestone by this many months.
    milestone_offset = models.IntegerField(default=0)

    # Flag that a bug has already been created for this package this cycle
    bug_filed_this_cycle = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Merge Bug Package Info"
        verbose_name_plural = "Merge Bug Package Info Sets"


class BackportBugPackageInfo(models.Model):
    """Information about a package or package group for creating a backport bug."""

    # Name of the package group - primary key
    name = models.CharField(primary_key=True, max_length=200)

    # Names of packages separated by commas
    package_names_combined = models.CharField(max_length=600, default="")

    # When creating a new merge board, offset the expected milestone by this many months.
    milestone_offset = models.IntegerField(default=0)

    # Description template for the bug
    description_template = models.TextField(default="")

    # Flag that a bug has already been created for this package this cycle
    bug_filed_this_cycle = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Backport Bug Package Info"
        verbose_name_plural = "Backport Bug Package Info Sets"

    @property
    def packages(self) -> list[str]:
        """Return the list of package names."""
        return [name.strip() for name in self.package_names_combined.split(",")]


class MergeBugFilterSettings(models.Model):
    """Sitewide settings defining required merge board bug attributes."""

    TYPE_MERGE = "merge"
    TYPE_BACKPORT = "backport"

    TYPE_CHOICES = [
        (TYPE_MERGE, "merge"),
        (TYPE_BACKPORT, "backport"),
    ]

    # The associated Django site
    site = models.ForeignKey(Site, on_delete=models.CASCADE)

    # Whether these settings apply to merge bugs or backport bugs
    settings_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_MERGE)

    tags_combined = models.CharField(max_length=600, default="")
    subscribers_combined = models.CharField(max_length=600, default="", blank=True)

    class Meta:
        verbose_name = "Merge Bug Filter Setting"
        verbose_name_plural = "Merge Bug Filter Settings"
        constraints = [
            models.UniqueConstraint(
                fields=["site", "settings_type"],
                name="unique_bug_filter_settings_per_site_and_type",
            )
        ]

    @property
    def tags(self) -> list[str]:
        """Return the list of tags."""
        return [tag.strip() for tag in self.tags_combined.split(",") if tag.strip()]

    @property
    def subscribers(self) -> list[str]:
        """Return the list of subscribers."""
        return [sub.strip() for sub in self.subscribers_combined.split(",") if sub.strip()]


class BackportBugFilterSettingsManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(settings_type=MergeBugFilterSettings.TYPE_BACKPORT)


class BackportBugFilterSettings(MergeBugFilterSettings):
    """Proxy for backport bug filter settings."""

    objects = BackportBugFilterSettingsManager()

    class Meta:
        proxy = True
        verbose_name = "Backport Bug Filter Setting"
        verbose_name_plural = "Backport Bug Filter Settings"


class WeeklyTask(models.Model):
    """A task to enqueue at a set time on a chosen set of days of the week."""

    TASK_REFRESH_REVIEWS = "refresh_reviews"
    TASK_PRUNE_TASK_RESULTS = "prune_task_results"
    TASK_REFRESH_MERGE_SCHEDULE = "refresh_merge_schedule"
    TASK_SUBMIT_MERGE_BUGS = "submit_merge_bugs"
    TASK_SUBMIT_BACKPORT_BUGS = "submit_backport_bugs"

    TASK_CHOICES = [
        (TASK_REFRESH_REVIEWS, "Refresh reviews"),
        (TASK_PRUNE_TASK_RESULTS, "Prune task results"),
        (TASK_REFRESH_MERGE_SCHEDULE, "Refresh merge schedule"),
        (TASK_SUBMIT_MERGE_BUGS, "Submit merge bugs"),
        (TASK_SUBMIT_BACKPORT_BUGS, "Submit backport bugs"),
    ]

    WEEKDAY_FIELDS = (
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    )

    task = models.CharField(max_length=50, choices=TASK_CHOICES)

    # Django user whose username is passed to the task when enqueued.
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)

    # Time of day to run the task.
    time_of_day = models.TimeField()

    # Days of the week on which the task activates.
    monday = models.BooleanField(default=False)
    tuesday = models.BooleanField(default=False)
    wednesday = models.BooleanField(default=False)
    thursday = models.BooleanField(default=False)
    friday = models.BooleanField(default=False)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)

    enabled = models.BooleanField(default=True)
    next_run = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Weekly Task"
        verbose_name_plural = "Weekly Tasks"
        ordering = ["time_of_day"]

    def __str__(self) -> str:
        return f"{self.get_task_display()} ({self.active_days_display()} {self.time_of_day})"

    def active_days_display(self) -> str:
        """Return a human-readable list of the active weekdays."""
        labels = [name.capitalize() for name in self.WEEKDAY_FIELDS if getattr(self, name)]
        return ", ".join(labels) if labels else "never"

    def runs_on(self, weekday: int) -> bool:
        """Return True if the task activates on *weekday* (Monday=0 .. Sunday=6)."""
        return bool(getattr(self, self.WEEKDAY_FIELDS[weekday]))

    def next_occurrence(self, after=None) -> datetime | None:
        """Return the next datetime after the specified time when this task should run."""
        after = after or timezone.now()
        local_after = timezone.localtime(after)
        tz = timezone.get_current_timezone()

        for offset in range(8):
            day = (local_after + timedelta(days=offset)).date()
            if not self.runs_on(day.weekday()):
                continue
            candidate = timezone.make_aware(datetime.combine(day, self.time_of_day), tz)
            if candidate > after:
                return candidate
        return None
