"""
URL configuration for pinot_noir project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView
from launchpad import views as launchpad_views
from merges_schedule import views as merges_schedule_views
from reviews import views as reviews_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", RedirectView.as_view(url="/merges-schedule", permanent=False), name="root-redirect"),
    path("merges-schedule", merges_schedule_views.index, name="merges-schedule"),
    path("reviews", reviews_views.index, name="reviews"),
    path(
        "launchpad/bug/new/<str:bug_type>",
        launchpad_views.new_bug,
        name="launchpad-mergebug",
    ),
]
