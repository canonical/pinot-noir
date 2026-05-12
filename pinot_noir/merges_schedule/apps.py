from django.apps import AppConfig


class MergesScheduleConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pinot_noir.merges_schedule"
    label = "merges_schedule"
