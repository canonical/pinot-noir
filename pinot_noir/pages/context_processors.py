from django.conf import settings
from django.urls import NoReverseMatch, reverse

from .models import PageMetadata


def nav_entries(request):
    """Expose the configured sidebar nav as ``nav_entries`` to all templates.

    Each entry resolves its URL from ``url_name`` so apps can move their
    routes without editing the base template. Entries whose ``PageMetadata``
    row has ``enabled=False`` are filtered out. ``is_active`` is set when the
    request path matches the entry's URL (or sits below it).
    """
    disabled_slugs = set(
        PageMetadata.objects.filter(enabled=False).values_list("slug", flat=True)
    )
    entries = []
    current_path = getattr(request, "path", "") or ""
    for entry in getattr(settings, "PINOT_NOIR_NAV", []):
        if entry["slug"] in disabled_slugs:
            continue
        try:
            url = reverse(entry["url_name"])
        except NoReverseMatch:
            url = entry.get("fallback_url", "#")
        entries.append(
            {
                "slug": entry["slug"],
                "label": entry["label"],
                "icon": entry.get("icon", ""),
                "url": url,
                "is_active": current_path == url
                or (url != "/" and current_path.startswith(url + "/")),
            }
        )
    return {"nav_entries": entries}
