from django.urls import path

from . import views

app_name = "site_admin"

urlpatterns = [
    path("", views.index, name="index"),
    path("tokens", views.tokens, name="tokens"),
    path("pages", views.pages, name="pages"),
    path("pages/<slug:slug>/toggle", views.toggle_page, name="toggle-page"),
]
