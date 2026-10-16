from django.apps import apps as django_apps
from django.db.models.signals import post_migrate

from .registry import get_pages


def ensure_page_metadata(sender, **kwargs):
    """Create a ``PageMetadata`` row for each registered page."""
    PageMetadata = django_apps.get_model("pages", "PageMetadata")
    for page in get_pages():
        PageMetadata.objects.get_or_create(slug=page.slug)


def connect(app_config):
    post_migrate.connect(ensure_page_metadata, sender=app_config)
