from django.urls import path

from . import views

app_name = "merges_schedule"

urlpatterns = [
    path("merges-schedule", views.index, name="index"),
]
