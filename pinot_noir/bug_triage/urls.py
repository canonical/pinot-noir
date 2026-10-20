from django.urls import path

from . import views
from .apps import PAGE_SLUG

app_name = "bug_triage"

urlpatterns = [
    path(PAGE_SLUG, views.index, name="index"),
]
