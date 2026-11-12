from django.urls import path

from . import views

app_name = "user_settings"

urlpatterns = [
    path("", views.index, name="index"),
    path("general", views.general, name="general"),
    path("tokens", views.tokens, name="tokens"),
]
