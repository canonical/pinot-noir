from django.apps import apps as django_apps
from django.conf import settings
from django.db.models.signals import post_migrate


def ensure_page_metadata(sender, **kwargs):
    """Create a ``PageMetadata`` row for each page in ``PINOT_NOIR_NAV``."""
    PageMetadata = django_apps.get_model("pages", "PageMetadata")
    for entry in getattr(settings, "PINOT_NOIR_NAV", []):
        PageMetadata.objects.get_or_create(slug=entry["slug"])


def connect(app_config):
    post_migrate.connect(ensure_page_metadata, sender=app_config)
