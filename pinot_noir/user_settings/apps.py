from django.apps import AppConfig


class UserSettingsConfig(AppConfig):
    """Settings pages available to every authenticated user."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "pinot_noir.user_settings"
    label = "user_settings"
