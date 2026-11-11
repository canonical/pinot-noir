from django.urls import URLPattern, URLResolver, include, path
from django.views.generic import RedirectView

from pinot_noir.pages.registry import get_pages

from . import views

app_name = "site_admin"

urlpatterns: list[URLPattern | URLResolver] = [
    path("", views.index, name="index"),
    path(
        "tokens",
        RedirectView.as_view(pattern_name="user_settings:tokens", permanent=False),
    ),
    path("pages", views.pages, name="pages"),
    path("pages/<slug:slug>/toggle", views.toggle_page, name="toggle-page"),
    path("team", views.team, name="team"),
]

# Pages own their admin section: /manage/<slug>/, namespace site_admin:<app label>.
urlpatterns += [
    path(f"{page.slug}/", include((page.manage_urls, page.app_label)))
    for page in get_pages()
    if page.manage_urls
]
