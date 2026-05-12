from django.contrib.auth.models import User
from django.db import models


class UserTokens(models.Model):
    """Tokens for a Django admin user to access external services."""

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
    package_names_combined = models.CharField(max_length=600)

    # When creating a new merge board, offset the expected milestone by this many months.
    milestone_offset = models.IntegerField(default=0)

    # Description template for the bug
    description_template = models.TextField(default="")

    @property
    def packages(self) -> list[str]:
        """Return the list of package names."""
        return [name.strip() for name in self.package_names_combined.split(",")]
