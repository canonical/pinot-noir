from django.urls import NoReverseMatch, reverse

from .models import PageMetadata
from .registry import get_pages


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
