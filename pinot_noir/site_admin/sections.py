"""The site admin's own side navigation."""

from dataclasses import dataclass

from django.urls import reverse

from pinot_noir.pages.registry import Page, get_pages


@dataclass(frozen=True)
class Section:
    url_name: str
    label: str


# Add new admin subpages here; the first one is the /manage/ landing page.
SECTIONS: tuple[Section, ...] = (
    Section("site_admin:team", "My team"),
    Section("site_admin:tokens", "My tokens"),
    Section("site_admin:pages", "Pages"),
)


def page_admin_url_name(page: Page) -> str:
    """URL name of a page's own admin section (see ``Page.manage_urls``)."""
    return f"site_admin:{page.app_label}:index"


def section_entries(current_path: str) -> list[dict]:
    """Side nav entries. Pages that own an admin section are nested under Pages."""
    entries = []
    for section in SECTIONS:
        url = reverse(section.url_name)
        entries.append(
            {
                "label": section.label,
                "url": url,
                "is_active": current_path == url,
                "children": [],
            }
        )
    pages_url = reverse("site_admin:pages")
    pages_entry = next(entry for entry in entries if entry["url"] == pages_url)
    for page in get_pages():
        if page.manage_urls:
            url = reverse(page_admin_url_name(page))
            pages_entry["children"].append(
                {"label": page.label, "url": url, "is_active": current_path.startswith(url)}
            )
    return entries
