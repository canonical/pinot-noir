from django.urls import path

from . import manage_views

urlpatterns = [path("", manage_views.index, name="index")]
