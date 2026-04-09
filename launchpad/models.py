from django.db import models


class LPUser(models.Model):
    """Launchpad user model.

    Username is the primary key and an optional email md5 is stored for Gravatar.
    """

    username = models.CharField(max_length=100, primary_key=True)
    email_md5 = models.CharField(max_length=32, blank=True, null=True)

    class Meta:
        verbose_name = "Launchpad user"
        verbose_name_plural = "Launchpad users"

    def __str__(self) -> str:
        return self.username

    @property
    def gravatar_url(self) -> str:
        """Return Gravatar URL when md5 available, otherwise an empty string."""
        if not self.email_md5:
            return ""
        return f"https://www.gravatar.com/avatar/{self.email_md5}"


class UbuntuRelease(models.Model):
    """Ubuntu release model."""

    adjective = models.CharField(max_length=30, unique=True)
    animal = models.CharField(max_length=30, unique=True)
    version = models.CharField(max_length=10, blank=True)

    class Meta:
        verbose_name = "Ubuntu release"
        verbose_name_plural = "Ubuntu releases"

    def __str__(self) -> str:
        return self.adjective
