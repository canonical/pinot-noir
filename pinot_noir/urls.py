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
    1. Import the include() function: from django.urls import path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from pinot_noir.launchpad import views as launchpad_views
from pinot_noir.pages.urls import page_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("manage/", include("pinot_noir.site_admin.urls")),
    path(
        "",
        RedirectView.as_view(pattern_name="merges_schedule:index", permanent=False),
        name="root-redirect",
    ),
    *page_urlpatterns(),
    path(
        "launchpad/bug/new/<str:bug_type>",
        launchpad_views.new_bug,
        name="launchpad-mergebug",
    ),
]
