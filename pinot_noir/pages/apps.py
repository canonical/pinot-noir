from django.apps import AppConfig


class PagesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pinot_noir.pages"
    label = "pages"

    def ready(self):
        from . import signals

        signals.connect(self)
