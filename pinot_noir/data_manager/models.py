from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.db import models

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


class LPReviewMarkerUser(models.Model):
    """A launchpad user that, when assigned to a review, makes it appear on the review board."""

    username = models.CharField(max_length=100, primary_key=True)


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
