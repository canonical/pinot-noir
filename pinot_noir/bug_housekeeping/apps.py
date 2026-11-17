from django.apps import AppConfig

from pinot_noir.pages.registry import Page

PAGE_SLUG = "bug-housekeeping"


class BugHousekeepingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pinot_noir.bug_housekeeping"
    label = "bug_housekeeping"
    page = Page(
        slug=PAGE_SLUG,
        label="Bug Housekeeping",
        icon="circle-of-friends",
        refresh_task="pinot_noir.bug_housekeeping.tasks.refresh_bug_housekeeping",
        manage_urls="pinot_noir.bug_housekeeping.manage_urls",
        order=40,
    )
