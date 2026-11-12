from django.db import models


class ReviewMarker(models.Model):
    """A Launchpad user or team whose assignment marks a review for the board."""

    username = models.CharField(max_length=100, primary_key=True)

    class Meta:
        verbose_name = "Review marker"
        verbose_name_plural = "Review markers"

    def __str__(self) -> str:
        return self.username


class UbuntuRelease(models.Model):
    """Ubuntu release model."""

    STATUS_DEVEL = "devel"
    STATUS_SUPPORTED = "supported"
    STATUS_EXTENDED_SUPPORT = "esm"
    STATUS_END_OF_LIFE = "eol"

    STATUS_CHOICES = [
        (STATUS_DEVEL, "devel"),
        (STATUS_SUPPORTED, "supported"),
        (STATUS_EXTENDED_SUPPORT, STATUS_EXTENDED_SUPPORT),
        (STATUS_END_OF_LIFE, STATUS_END_OF_LIFE),
    ]

    # Release name
    adjective = models.CharField(max_length=30, unique=True)
    animal = models.CharField(max_length=30, unique=True)

    # Release version - 2X.XX
    version = models.CharField(max_length=10, blank=True)

    # Release status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DEVEL)

    class Meta:
        verbose_name = "Ubuntu release"
        verbose_name_plural = "Ubuntu releases"

    def __str__(self) -> str:
        return self.adjective
