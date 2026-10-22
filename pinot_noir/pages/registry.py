"""Registry of data pages declared by installed apps.

A page app declares itself by setting ``page = Page(...)`` on its AppConfig.
Everything that needs to know about pages (sidebar nav, root URLconf,
PageMetadata rows, the weekly scheduler, ``refresh_page``) reads from here, so
adding a page only means adding the app to ``INSTALLED_APPS``.
"""

from dataclasses import dataclass, replace

from django.apps import apps
from django.utils.module_loading import import_string


@dataclass(frozen=True)
class Page:
    """Static description of a data page.

    ``slug`` is the PageMetadata key and the URL path. ``refresh_task`` is the
    dotted path to the page's ``@task`` that refreshes its data (imported
    lazily, since AppConfigs load before models). ``manage_urls`` is the dotted
    path to the page's own site admin URLconf, mounted at ``/manage/<slug>/``
    under the ``site_admin:<app label>`` namespace. ``app_name``, ``app_label``
    and ``url_name`` are filled in by :func:`get_pages` from the AppConfig.
    """

    slug: str
    label: str
    icon: str = "circle-of-friends"
    refresh_task: str | None = None
    manage_urls: str | None = None
    order: int = 100
    app_name: str = ""
    app_label: str = ""
    url_name: str = ""

    def get_refresh_task(self):
        return import_string(self.refresh_task) if self.refresh_task else None

    @property
    def refresh_task_name(self) -> str | None:
        return self.refresh_task.rsplit(".", 1)[-1] if self.refresh_task else None


def get_pages() -> list[Page]:
    """Return every declared page, ordered by ``order`` then label."""
    pages = []
    for config in apps.get_app_configs():
        page = getattr(config, "page", None)
        if isinstance(page, Page):
            pages.append(
                replace(
                    page,
                    app_name=config.name,
                    app_label=config.label,
                    url_name=f"{config.label}:index",
                )
            )
    return sorted(pages, key=lambda p: (p.order, p.label))


def get_page(slug: str) -> Page | None:
    return next((p for p in get_pages() if p.slug == slug), None)
