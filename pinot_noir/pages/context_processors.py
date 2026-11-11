from urllib.parse import urljoin

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.urls import NoReverseMatch, reverse

from .management.commands.collectstatic import VANILLA_CSS, VANILLA_URL
from .models import PageMetadata
from .registry import get_pages


def vanilla_css(request):
    """Use the CDN in development and collected Vanilla CSS in production."""
    if settings.DEBUG:
        return {"vanilla_css_url": VANILLA_URL}
    try:
        if staticfiles_storage.exists(VANILLA_CSS):
            # Manifest URL rewriting corrupts fragment references in Vanilla's SVG data URIs.
            # The versioned filename already provides cache busting.
            url = urljoin(urljoin("/", settings.STATIC_URL), VANILLA_CSS)
        else:
            url = VANILLA_URL
    except (OSError, ValueError):
        url = VANILLA_URL
    return {"vanilla_css_url": url}


def nav_entries(request):
    """Expose the sidebar nav as ``nav_entries`` to all templates.

    Entries come from the page registry (``page`` on each AppConfig). Pages
    whose ``PageMetadata`` row has ``enabled=False`` are filtered out.
    ``is_active`` is set when the request path matches the entry's URL (or
    sits below it).
    """
    disabled_slugs = set(PageMetadata.objects.filter(enabled=False).values_list("slug", flat=True))
    entries = []
    current_path = getattr(request, "path", "") or ""
    for page in get_pages():
        if page.slug in disabled_slugs:
            continue
        try:
            url = reverse(page.url_name)
        except NoReverseMatch:
            url = "#"
        entries.append(
            {
                "slug": page.slug,
                "label": page.label,
                "icon": page.icon,
                "url": url,
                "is_active": current_path == url
                or (url != "/" and current_path.startswith(url + "/")),
            }
        )
    return {"nav_entries": entries}
