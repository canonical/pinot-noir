from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.db import models


class UserTokens(models.Model):
    """Tokens for a Django admin user to access external services."""

    class Meta:
        verbose_name = "User Tokens"
        verbose_name_plural = "User Token Groups"

    # The associated Django admin user
    user = models.OneToOneField(User, on_delete=models.CASCADE)

    # Lauchpad API credentials string
    lp_token = models.CharField(max_length=1000)


class MergeBugPackageInfo(models.Model):
    """Information about a package for creating a merges schedule merge bug."""

    # Name of package - primary key
    package = models.CharField(primary_key=True, max_length=200)

    # When creating a new merge board, offset the expected milestone by this many months.
    milestone_offset = models.IntegerField(default=0)


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

    @property
    def packages(self) -> list[str]:
        """Return the list of package names."""
        return [name.strip() for name in self.package_names_combined.split(",")]


class LPReviewMarkerUser(models.Model):
    """A launchpad user that, when assigned to a review, makes it appear on the review board."""

    username = models.CharField(max_length=100, primary_key=True)


class MergeBugFilterSettings(models.Model):
    """Sitewide settings defining required merge board bug attributes."""

    # The associated Django site to make this a singleton model
    site = models.OneToOneField(Site, on_delete=models.CASCADE)

    tags_combined = models.CharField(max_length=600, default="")
    subscribers_combined = models.CharField(max_length=600, default="")

    class Meta:
        verbose_name = "Merge Bug Filter Setting"
        verbose_name_plural = "Merge Bug Filter Settings"

    @property
    def tags(self) -> list[str]:
        """Return the list of tags."""
        return [tag.strip() for tag in self.tags_combined.split(",") if tag.strip()]

    @property
    def subscribers(self) -> list[str]:
        """Return the list of subscribers."""
        return [sub.strip() for sub in self.subscribers_combined.split(",") if sub.strip()]
