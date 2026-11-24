from django.urls import path

from . import views
from .apps import PAGE_SLUG

app_name = "bug_triage"

urlpatterns = [
    path(PAGE_SLUG, views.index, name="index"),
    path(f"{PAGE_SLUG}/report.html", views.report, name="report"),
    path(f"{PAGE_SLUG}/download", views.download, name="download"),
]
