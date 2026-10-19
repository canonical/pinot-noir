from django.apps import AppConfig

from pinot_noir.pages.registry import Page

PAGE_SLUG = "merges-schedule"


class MergesScheduleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pinot_noir.merges_schedule"
    label = "merges_schedule"
    page = Page(
        slug=PAGE_SLUG,
        label="Merge Schedule",
        refresh_task="pinot_noir.merges_schedule.tasks.refresh_merge_schedule",
        order=10,
    )
