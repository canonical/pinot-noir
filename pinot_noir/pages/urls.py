"""URL patterns for every registered page app."""

from django.urls import include, path

from .registry import get_pages


def page_urlpatterns() -> list:
    return [path("", include(f"{page.app_name}.urls")) for page in get_pages()]
