from django.apps import AppConfig

from pinot_noir.pages.registry import Page

PAGE_SLUG = "bug-triage"


class BugTriageConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pinot_noir.bug_triage"
    label = "bug_triage"
    page = Page(
        slug=PAGE_SLUG,
        label="Bug Triage",
        icon="circle-of-friends",
        refresh_task="pinot_noir.bug_triage.tasks.refresh_bug_triage",
        manage_urls="pinot_noir.bug_triage.manage_urls",
        order=30,
    )
