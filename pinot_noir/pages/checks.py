"""System checks that catch page misconfiguration at startup."""

from django.core.checks import Error, register
from django.urls import NoReverseMatch, reverse
from django.utils.text import slugify

from .registry import get_pages


@register()
def check_pages(app_configs, **kwargs):  # noqa: ARG001
    errors = []
    seen: dict[str, str] = {}
    for page in get_pages():
        obj = page.app_name
        if page.slug != slugify(page.slug):
            errors.append(
                Error(f"Page slug {page.slug!r} is not a valid slug.", obj=obj, id="pages.E001")
            )
        if page.slug in seen:
            errors.append(
                Error(
                    f"Page slug {page.slug!r} is also used by {seen[page.slug]}.",
                    obj=obj,
                    id="pages.E002",
                )
            )
        seen[page.slug] = obj
        try:
            url = reverse(page.url_name)
        except NoReverseMatch:
            errors.append(
                Error(
                    f"Page URL {page.url_name!r} does not resolve.",
                    hint=(
                        "Give the app a urls.py with app_name = <app label> "
                        "and a route named 'index'."
                    ),
                    obj=obj,
                    id="pages.E003",
                )
            )
        else:
            if url.strip("/") != page.slug:
                errors.append(
                    Error(
                        f"Page URL {url!r} does not match slug {page.slug!r}.",
                        hint="Route the index view at path(PAGE_SLUG, ...).",
                        obj=obj,
                        id="pages.E004",
                    )
                )
        if page.refresh_task:
            try:
                task = page.get_refresh_task()
            except ImportError as exc:
                errors.append(
                    Error(f"Refresh task import failed: {exc}", obj=obj, id="pages.E005")
                )
            else:
                if not hasattr(task, "enqueue"):
                    errors.append(
                        Error(
                            f"{page.refresh_task} is not a @task.",
                            obj=obj,
                            id="pages.E006",
                        )
                    )
    return errors
