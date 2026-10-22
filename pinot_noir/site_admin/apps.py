from django.apps import AppConfig


class SiteAdminConfig(AppConfig):
    """Pinot Noir admin settings pages."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "pinot_noir.site_admin"
    label = "site_admin"
