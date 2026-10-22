"""Site admin URLs for this page, mounted at /manage/<slug>/ (see Page.manage_urls)."""

from django.urls import path

from . import manage_views

urlpatterns = [
    path("", manage_views.index, name="index"),
]
