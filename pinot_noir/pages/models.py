from django.db import models
from django.utils import timezone


class PageMetadata(models.Model):
    """Per-page persistent state.

    Each data page (merges schedule, reviews, ...) gets a single row keyed by
    a stable ``slug``. Pages refresh their backing data via background tasks
    or management commands; those code paths call :meth:`touch` to record
    when a refresh succeeded. When ``enabled`` is false the page is hidden
    from the sidebar navigation.
    """

    slug = models.SlugField(max_length=100, primary_key=True)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "page metadata"

    def __str__(self) -> str:
        return self.slug

    @classmethod
    def touch(cls, slug: str) -> "PageMetadata":
        meta, _ = cls.objects.get_or_create(slug=slug)
        meta.last_refreshed_at = timezone.now()
        meta.save(update_fields=["last_refreshed_at"])
        return meta
