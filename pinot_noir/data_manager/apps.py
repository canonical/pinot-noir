from django.apps import AppConfig


class DataManagerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pinot_noir.data_manager"
    label = "data_manager"
